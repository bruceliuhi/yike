import {spawn, type ChildProcessWithoutNullStreams} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {lstatSync} from 'node:fs';
import {win32 as path} from 'node:path';
import {validNativeAccount} from '../shared/platformAccount';
import type {PlatformLoginDriverOptions} from './platformLoginDriver';
import type {SourceViewRun, SourceViewStart} from './sourceViewController';

const SCHEMA = 'windows-source-view-v1';
const MAX_OUTPUT = 16 * 1024;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const NOTE_ID = /^[0-9a-f]{24}$/;
const SAFE_CODES = new Set(['XHS_SOURCE_INVALID_INPUT', 'XHS_SOURCE_CANCELLED', 'XHS_SOURCE_ORIGIN_CHANGED',
  'XHS_SOURCE_ACCOUNT_CHANGED', 'XHS_SOURCE_PLATFORM_BLOCKED', 'XHS_SOURCE_SEARCH_UNAVAILABLE',
  'XHS_SOURCE_NOT_FOUND', 'XHS_SOURCE_DETAIL_UNAVAILABLE', 'XHS_SOURCE_UNAVAILABLE',
  'XHS_SOURCE_TIMED_OUT', 'XHS_SOURCE_BUSY', 'SOURCE_HOST_FAILED']);
const failure = (code: string) => new Error(code);

/** All frame fields are strings; even escaped duplicate keys are rejected. */
function decodeFrame(bytes: Buffer): Record<string, string> {
  const text = new TextDecoder('utf-8', {fatal: true}).decode(bytes).trim();
  const value: unknown = JSON.parse(text);
  if (!value || typeof value !== 'object' || Array.isArray(value) || text[0] !== '{') throw failure('SOURCE_HOST_FAILED');
  const pair = /\s*("(?:[^"\\]|\\.)*")\s*:\s*("(?:[^"\\]|\\.)*")\s*/y;
  const keys = new Set<string>();
  let offset = 1;
  while (true) {
    pair.lastIndex = offset;
    const match = pair.exec(text);
    if (!match) throw failure('SOURCE_HOST_FAILED');
    const key: string = JSON.parse(match[1]);
    if (keys.has(key)) throw failure('SOURCE_HOST_FAILED');
    keys.add(key); offset = pair.lastIndex;
    if (text[offset] === '}' && offset === text.length - 1) break;
    if (text[offset++] !== ',') throw failure('SOURCE_HOST_FAILED');
  }
  const result = value as Record<string, string>;
  if (result.schema_version !== SCHEMA) throw failure('SOURCE_HOST_FAILED');
  return result;
}

function validateInput(options: PlatformLoginDriverOptions, input: SourceViewStart): void {
  if (typeof input.profileId !== 'string' || !UUID.test(input.profileId) ||
      typeof input.expectedAccount !== 'string' || !validNativeAccount('XIAOHONGSHU', input.expectedAccount) ||
      typeof input.noteId !== 'string' || !NOTE_ID.test(input.noteId) ||
      (input.authorId !== null && (typeof input.authorId !== 'string' || !NOTE_ID.test(input.authorId))) ||
      (input.originalQuery !== null && (typeof input.originalQuery !== 'string' || !input.originalQuery.trim() ||
        Array.from(input.originalQuery).length > 200 || /[\p{Cc}\p{Cf}\p{Cs}]/u.test(input.originalQuery))) ||
      (input.authorId === null && input.originalQuery === null)) throw failure('XHS_SOURCE_INVALID_INPUT');
  for (const key of ['pythonExecutable', 'projectRoot', 'runtimePath', 'profileRoot', 'outputRoot'] as const) {
    const value = options[key];
    if (typeof value !== 'string' || !/^[A-Za-z]:[\\/]/.test(value) || !path.isAbsolute(value) ||
        /[\p{Cc}\p{Cf}\p{Cs}]/u.test(value)) throw failure('XHS_SOURCE_INVALID_INPUT');
    const info = lstatSync(value);
    if (info.isSymbolicLink() || (key === 'pythonExecutable' ? !info.isFile() : !info.isDirectory())) throw failure('XHS_SOURCE_INVALID_INPUT');
  }
  const roots = [options.runtimePath, options.profileRoot, options.outputRoot].map(p => path.resolve(p).toLowerCase());
  for (let i = 0; i < roots.length; i++) for (let j = i + 1; j < roots.length; j++) {
    if (roots[i] === roots[j] || roots[i].startsWith(roots[j] + '\\') || roots[j].startsWith(roots[i] + '\\')) throw failure('XHS_SOURCE_INVALID_INPUT');
  }
}

/** Browser readiness is host-verified; successful stop additionally requires a clean physical close. */
export function createSourceViewDriver(options: PlatformLoginDriverOptions) {
  const owned = {...options};
  const launch = owned.spawn ?? spawn;
  return {start(input: SourceViewStart): SourceViewRun {
    // Snapshot main-owned target fields before deferred launch.
    const target = {...input};
    const {signal} = target;
    let child: ChildProcessWithoutNullStreams | null = null;
    let settled = false, sawOpened = false, openedResolved = false, unknownCleanup = false;
    let cancelled = signal?.aborted ?? false;
    let reason: Error | undefined;
    let terminal: Record<string, string> | null = null;
    let deadline: ReturnType<typeof setTimeout> | undefined;
    let grace: ReturnType<typeof setTimeout> | undefined;
    let resolveOpened!: () => void, rejectOpened!: (error: Error) => void;
    let resolveCompleted!: () => void, rejectCompleted!: (error: Error) => void;
    const opened = new Promise<void>((resolve, reject) => {resolveOpened = resolve; rejectOpened = reject;});
    const completed = new Promise<void>((resolve, reject) => {resolveCompleted = resolve; rejectCompleted = reject;});
    void opened.catch(() => {}); void completed.catch(() => {});

    function settle(error?: Error) {
      if (settled) return;
      settled = true;
      if (deadline) clearTimeout(deadline);
      if (grace) clearTimeout(grace);
      signal?.removeEventListener('abort', onAbort);
      if (!openedResolved) rejectOpened(error ?? failure('SOURCE_HOST_FAILED'));
      if (error) rejectCompleted(error); else resolveCompleted();
    }
    function requestStop(error?: Error) {
      if (settled) return;
      cancelled = true;
      reason ??= error;
      if (!child || grace) return;
      const active = child;
      grace = setTimeout(() => {
        unknownCleanup = true;
        try {active.kill();} catch { /* One process kill cannot prove browser-tree cleanup. */ }
        settle(failure('SOURCE_STOP_FAILED'));
      }, 30_000);
      try {active.stdin.end();} catch {unknownCleanup = true; reason = failure('SOURCE_HOST_FAILED');}
    }
    function onAbort() {requestStop(failure('XHS_SOURCE_CANCELLED'));}
    function protocolFailure() {
      unknownCleanup = true;
      reason = failure('SOURCE_HOST_FAILED');
      requestStop(reason);
    }
    signal?.addEventListener('abort', onAbort, {once: true});
    void Promise.resolve().then(() => {
      if (cancelled) {settle(failure('XHS_SOURCE_CANCELLED')); return;}
      let wire: Buffer;
      try {
        validateInput(owned, target);
        wire = Buffer.from(JSON.stringify({schema_version: SCHEMA, runtime_path: owned.runtimePath,
          profile_path: path.join(owned.profileRoot, target.profileId), output_path: path.join(owned.outputRoot, randomUUID()),
          timeout_seconds: 300, note_id: target.noteId, expected_account: target.expectedAccount,
          author_id: target.authorId, original_query: target.originalQuery}) + '\n', 'utf8');
        if (wire.length > 65536) throw failure('XHS_SOURCE_INVALID_INPUT');
      } catch {settle(failure('XHS_SOURCE_INVALID_INPUT')); return;}
      const env: NodeJS.ProcessEnv = {PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1'};
      for (const key of ['SystemRoot', 'WINDIR', 'USERNAME']) if (process.env[key]) env[key] = process.env[key];
      try {
        child = launch(owned.pythonExecutable, ['-B', '-X', 'utf8', '-m', 'app.windows_source_view'],
          {cwd: owned.projectRoot, shell: false, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'], env});
      } catch {unknownCleanup = true; settle(failure('SOURCE_HOST_FAILED')); return;}
      const active = child;
      let total = 0, pending = Buffer.alloc(0);
      deadline = setTimeout(() => requestStop(failure('XHS_SOURCE_TIMED_OUT')), 300_000);
      active.stderr.resume(); // Drain without retaining or exposing raw host logs.
      active.on('error', protocolFailure);
      active.stdin.on('error', protocolFailure);
      active.stdout.on('error', protocolFailure);
      active.stderr.on('error', protocolFailure);
      active.stdout.on('data', (chunk: Buffer) => {
        if (settled || unknownCleanup) return;
        total += chunk.length;
        if (total > MAX_OUTPUT) {protocolFailure(); return;}
        pending = Buffer.concat([pending, chunk]);
        try {
          let end: number;
          while ((end = pending.indexOf(10)) >= 0) {
            if (terminal) throw failure('SOURCE_HOST_FAILED');
            const frame = decodeFrame(pending.subarray(0, end));
            pending = pending.subarray(end + 1);
            const keys = Object.keys(frame).sort().join(',');
            if (frame.state === 'SOURCE_OPENED' && keys === 'schema_version,state' && !sawOpened) {
              sawOpened = true;
              if (!cancelled) {openedResolved = true; resolveOpened();}
            } else if (frame.state === 'CLOSED' && sawOpened && keys === 'schema_version,state') {
              terminal = frame;
            } else if (keys === 'error_code,schema_version,state' && SAFE_CODES.has(frame.error_code) &&
                (frame.state === 'FAILED' && frame.error_code !== 'XHS_SOURCE_CANCELLED' && frame.error_code !== 'XHS_SOURCE_TIMED_OUT' ||
                 frame.state === 'CANCELLED' && frame.error_code === 'XHS_SOURCE_CANCELLED' ||
                 frame.state === 'TIMED_OUT' && frame.error_code === 'XHS_SOURCE_TIMED_OUT')) {
              terminal = frame;
              if (frame.error_code === 'SOURCE_HOST_FAILED') unknownCleanup = true;
            } else throw failure('SOURCE_HOST_FAILED');
          }
          if (terminal && pending.length) throw failure('SOURCE_HOST_FAILED');
        } catch {protocolFailure();}
      });
      active.on('close', (code, terminationSignal) => {
        if (settled) return;
        if (code !== 0 || terminationSignal || !terminal || pending.length) unknownCleanup = true;
        if (unknownCleanup) {settle(failure('SOURCE_HOST_FAILED')); return;}
        if (cancelled) {settle(reason ?? failure('XHS_SOURCE_CANCELLED')); return;}
        if (terminal!.state === 'CLOSED') settle();
        else settle(failure(terminal!.error_code));
      });
      try {active.stdin.write(wire);} catch {protocolFailure();}
      if (cancelled) requestStop(reason);
    }).catch(() => {
      if (child) protocolFailure();
      else {unknownCleanup = true; settle(failure('SOURCE_HOST_FAILED'));}
    });
    return {opened, completed, async stop() {
      requestStop(failure('XHS_SOURCE_CANCELLED'));
      await completed.catch(() => {});
      if (unknownCleanup) throw failure('SOURCE_STOP_FAILED');
    }};
  }};
}
