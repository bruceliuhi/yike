import {spawn, type ChildProcessWithoutNullStreams} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {win32 as path} from 'node:path';
import type {CollectionDriver} from './collectionWorker';
import {candidateSubmissionSchema, type CandidateSubmission} from '../shared/candidateSubmission';
import {strategyConfigurationSchema} from '../shared/researchStrategies';
import {executionReceiptSchema} from '../shared/executionReceipt';

type Input = Parameters<CollectionDriver['start']>[0];
interface Options {
  pythonExecutable: string; projectRoot: string; runtimePath: string; profilePath: string; outputRoot: string;
  binding: {deviceId: string; credentialVersion: number} & Input['target'];
}
const SCHEMA = 'windows-source-host-v1';
const MAX_FRAME = 4 * 1024 * 1024;
const failure = (code = 'SOURCE_DRIVER_FAILED') => new Error(code);
const integer = (n: number, max: number) => Number.isInteger(n) && n >= 1 && n <= max;

/** Main-owned paths and account binding only. This adapter grants no capability. */
export function createPythonCollectionDriver(options: Options): CollectionDriver {
  const owned = structuredClone(options);
  return {start(original) {
    const {signal} = original;
    let child: ChildProcessWithoutNullStreams | null = null;
    let cancelled = signal.aborted;
    let stopFailed = false;
    let forceTimer: ReturnType<typeof setTimeout> | undefined;
    let deadlineTimer: ReturnType<typeof setTimeout> | undefined;
    let timedOut = false;
    let finishForced: (() => void) | null = null;
    function requestStop() {
      cancelled = true;
      if (!child || forceTimer) return;
      const active = child;
      active.stdin.end();
      forceTimer = setTimeout(() => {
        stopFailed = true;
        active.kill();
        finishForced?.();
      }, 30_000);
    }
    signal.addEventListener('abort', requestStop, {once: true});
    function invoke(payload: object): Promise<unknown> {
      return new Promise((resolve, reject) => {
        const frame = Buffer.from(JSON.stringify(payload) + '\n', 'utf8');
        if (frame.length > 65536) {reject(failure('SOURCE_DRIVER_INVALID_INPUT')); return;}
        const env: NodeJS.ProcessEnv = {PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1'};
        for (const key of ['SystemRoot', 'WINDIR', 'USERNAME']) if (process.env[key]) env[key] = process.env[key];
        const active = spawn(owned.pythonExecutable, ['-X', 'utf8', '-m', 'app.windows_collection_host'],
          {cwd: owned.projectRoot, shell: false, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'], env});
        child = active;
        let bytes = 0, invalid = false, settled = false;
        const chunks: Buffer[] = [];
        const settle = (error?: Error, value?: unknown) => {
          if (settled) return;
          settled = true; child = null; finishForced = null;
          if (forceTimer) clearTimeout(forceTimer); forceTimer = undefined;
          if (error) reject(error); else resolve(value);
        };
        finishForced = () => settle(failure('SOURCE_STOP_FAILED'));
        active.stdout.on('data', (chunk: Buffer) => {
          bytes += chunk.length;
          if (bytes > MAX_FRAME) {invalid = true; requestStop();} else chunks.push(chunk);
        });
        active.stderr.resume(); // Drain without retaining or disclosing upstream logs.
        active.stdin.on('error', () => {invalid = true; requestStop();});
        active.on('error', () => {invalid = true;});
        active.on('close', (code, terminationSignal) => {
          if (code !== 0 || terminationSignal) {stopFailed = true; settle(failure()); return;}
          if (invalid) {settle(failure()); return;}
          try {
            const text = new TextDecoder('utf-8', {fatal: true}).decode(Buffer.concat(chunks));
            if (!text.endsWith('\n') || text.indexOf('\n') !== text.length - 1) throw failure();
            const result = JSON.parse(text);
            if (!result || result.schema_version !== SCHEMA) throw failure();
            const keys = Object.keys(result).sort().join(',');
            if (result.state === 'COLLECTED' && keys === 'records,schema_version,state') settle(undefined, result.records);
            else if (['CANCELLED', 'TIMED_OUT', 'BLOCKED_INPUT', 'FAILED'].includes(result.state) &&
                (keys === 'schema_version,state' || keys === 'error_code,schema_version,state' &&
                 typeof result.error_code === 'string' && /^[A-Z_]{1,80}$/.test(result.error_code))) {
              if (result.error_code === 'SOURCE_HOST_FAILED') stopFailed = true;
              settle(failure(result.state === 'CANCELLED' ? 'SOURCE_DRIVER_CANCELLED' : result.state === 'TIMED_OUT' ? 'SOURCE_DRIVER_TIMED_OUT' : 'SOURCE_DRIVER_FAILED'));
            } else throw failure();
          } catch {settle(failure());}
        });
        active.stdin.write(frame);
        if (cancelled) requestStop();
      });
    }
    // Defer process creation until after the synchronous stop handle exists.
    const completed = Promise.resolve().then(async () => {
      const input = structuredClone({snapshot: original.snapshot, target: original.target, lease: original.lease, maxRecords: original.maxRecords});
      const {snapshot, target, maxRecords} = input;
      let mapping: Omit<CandidateSubmission, 'schema_version' | 'platform' | 'records'>;
      try {
        const c = strategyConfigurationSchema.parse(snapshot.configuration);
        const lease = executionReceiptSchema.parse(input.lease);
        if (lease.operation !== 'CLAIM' && lease.operation !== 'RENEW') throw failure();
        if (c.mode !== 'once' || c.schedule !== null || c.source !== 'search' || c.links.length || c.exclusions.length || c.research !== null ||
            c.keywords.some(q => q !== q.trim() || q.includes(',')) ||
            !integer(maxRecords, 100) || !integer(snapshot.max_records, 10000) || maxRecords > snapshot.max_records ||
            !integer(snapshot.max_runtime_seconds, 86400) || !snapshot.platforms.includes(target.platform) ||
            !['XIAOHONGSHU', 'DOUYIN', 'BILIBILI'].includes(target.platform) || target.access_mode !== 'PLATFORM_ACCOUNT' ||
            (['platform', 'access_mode', 'connection_id', 'connection_version'] as const).some(k => target[k] !== owned.binding[k])) throw failure();
        for (const value of [owned.pythonExecutable, owned.projectRoot, owned.runtimePath, owned.profilePath, owned.outputRoot])
          if (!/^[A-Za-z]:[\\/]/.test(value) || !path.isAbsolute(value) || /[\p{Cc}\p{Cf}\p{Cs}]/u.test(value)) throw failure();
        const batch = candidateSubmissionSchema.parse({schema_version: 'candidate-upload-v1', request_id: randomUUID(), platform: target.platform,
          profile_version_id: snapshot.profile_version_id, strategy_version_id: snapshot.strategy_version_id,
          execution: {device_id: owned.binding.deviceId, credential_version: owned.binding.credentialVersion, task_id: lease.task_id,
            run_id: lease.run_id, platform_run_id: lease.platform_run_id, lease_id: lease.lease_id, execution_generation: lease.execution_generation,
            access_mode: target.access_mode, connection_id: target.connection_id, connection_version: target.connection_version}, records: []});
        mapping = {request_id: batch.request_id, profile_version_id: batch.profile_version_id, strategy_version_id: batch.strategy_version_id, execution: batch.execution};
      } catch {throw failure('SOURCE_DRIVER_INVALID_INPUT');}
      const deadline = performance.now() + Math.min(snapshot.max_runtime_seconds, 900) * 1000;
      deadlineTimer = setTimeout(() => {timedOut = true; requestStop();}, Math.min(snapshot.max_runtime_seconds, 900) * 1000);
      const records: CandidateSubmission['records'] = [];
      let spent = 0;
      const seen = new Map<string, string>();
      const queries = snapshot.configuration.keywords;
      for (let index = 0; index < queries.length && spent < maxRecords; index++) {
        if (cancelled) throw failure(timedOut ? 'SOURCE_DRIVER_TIMED_OUT' : 'SOURCE_DRIVER_CANCELLED');
        const seconds = Math.ceil((deadline - performance.now()) / 1000);
        if (seconds < 1) throw failure('SOURCE_DRIVER_TIMED_OUT');
        const query = queries[index];
        const cap = Math.ceil((maxRecords - spent) / (queries.length - index));
        let result: unknown;
        try {result = await invoke({schema_version: SCHEMA, runtime_path: owned.runtimePath, profile_path: owned.profilePath,
          output_path: path.join(owned.outputRoot, randomUUID()), platform: target.platform, query, max_records: cap,
          timeout_seconds: seconds, mapping: {...mapping, request_id: randomUUID()}});}
        catch (error) {if (timedOut) throw failure('SOURCE_DRIVER_TIMED_OUT'); throw error;}
        if (cancelled) throw failure(timedOut ? 'SOURCE_DRIVER_TIMED_OUT' : 'SOURCE_DRIVER_CANCELLED');
        let parsed: CandidateSubmission['records'];
        try {
          parsed = candidateSubmissionSchema.parse({...mapping, schema_version: 'candidate-upload-v1', platform: target.platform, records: result}).records;
          if (parsed.length > cap || parsed.some(r => r.query !== query)) throw failure();
        } catch {throw failure();}
        spent += parsed.length;
        for (const record of parsed) {
          const key = JSON.stringify([record.kind, record.external_source_id, record.external_comment_id]);
          const {observed_at: _observed, query: _query, ...evidence} = record;
          const content = JSON.stringify(evidence);
          if (seen.has(key)) {if (seen.get(key) !== content) throw failure('SOURCE_DRIVER_CONFLICT');}
          else {seen.set(key, content); records.push(record);}
        }
      }
      return records;
    }).finally(() => {
      signal.removeEventListener('abort', requestStop);
      if (deadlineTimer) clearTimeout(deadlineTimer);
    });
    void completed.catch(() => {}); // An abort may precede the worker attaching its race handler.
    return {completed, async stop() {
      requestStop();
      await completed.catch(() => {});
      if (stopFailed) throw failure('SOURCE_STOP_FAILED');
    }};
  }};
}
