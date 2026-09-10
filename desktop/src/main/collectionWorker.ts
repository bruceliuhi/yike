import {createHash, randomUUID} from 'node:crypto';
import type {DeviceWorkerScope} from './deviceIdentityController';
import type {createExecutionSession} from './executionSession';
import type {createCandidateSession} from './candidateSession';
import {executionOperationSchema, type ExecutionOperation} from '../shared/executionOperation';
import {parseExecutionReceipt, type ExecutionReceipt} from '../shared/executionReceipt';
import {strategyViewSchema, type StrategyView} from '../shared/researchStrategies';
import {candidateSubmissionSchema, type CandidateSubmission} from '../shared/candidateSubmission';

type Lease = Extract<ExecutionReceipt, {operation: 'CLAIM' | 'RENEW'}>;
type RecoveryKey = {platformRunId: string; requestId: string};
type StopReason = 'CANCELLED' | 'SESSION_CHANGED' | 'LEASE_EXPIRED' | 'LEASE_UNKNOWN';
export type CollectionWorkerResult = {state: 'COMPLETED'; taskCompleted: boolean; requestId: string; recoveryKey: RecoveryKey} | ({taskCompleted: false} & (
  | {state: 'UPLOADED'; recoveryKey: RecoveryKey}
  | {state: 'UPLOAD_UNKNOWN'; recoveryKey: RecoveryKey}
  | {state: 'FINISH_UNKNOWN'; requestId: string; recoveryKey: RecoveryKey}
  | {state: 'LEASE_UNKNOWN'; requestId: string}
  | {state: 'STOPPED'; reason: StopReason; requestId?: string; recoveryKey?: RecoveryKey}
  | {state: 'BUSY'}
  | {state: 'FAILED'; error: 'COLLECTION_WORKER_INVALID_INPUT' | 'COLLECTION_WORKER_FAILED' | 'SOURCE_STOP_FAILED'; recoveryKey?: RecoveryKey}
));
export interface CollectionDriver {
  // Synchronous handle creation guarantees there is always a stop handle once
  // any source process starts. The driver owns raw output preservation/cleanup.
  start(input: {snapshot: StrategyView['snapshot']; target: NonNullable<ExecutionOperation['targets']>[number];
    lease: Lease; maxRecords: number; signal: AbortSignal}): {completed: Promise<unknown[]>; stop(): Promise<void>};
}
export interface CollectionWorkerOptions {
  execution: Pick<ReturnType<typeof createExecutionSession>, 'submit'>;
  candidates: Pick<ReturnType<typeof createCandidateSession>, 'submit'>;
  driver: CollectionDriver;
}
function canonical(value: unknown): string {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value !== null && typeof value === 'object') return '{' + Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)
    .map(([key, item]) => JSON.stringify(key) + ':' + canonical(item)).join(',') + '}';
  return JSON.stringify(value);
}

/** One foreground-confirmed platform at a time. No source capability is granted here. */
export function createCollectionWorker({execution, candidates, driver}: CollectionWorkerOptions) {
  let cancelActive: (() => void) | null = null;
  return {
    cancel() {cancelActive?.();},
    async run(input: {scope: DeviceWorkerScope; start: unknown; startReceipt: unknown; strategy: unknown;
      platformRunId: string;allowMonitor?:boolean;platformMaxRecords?:number}): Promise<CollectionWorkerResult> {
      if (cancelActive) return {state: 'BUSY', taskCompleted: false};
      const {scope} = input;
      const abort = new AbortController();
      let reason: StopReason | null = null;
      let scopeClosed = false;
      let recoveryKey: RecoveryKey | undefined;
      let requestId: string | undefined;
      let process: ReturnType<CollectionDriver['start']> | null = null;
      let stopPromise: Promise<void> | null = null;
      let timer: ReturnType<typeof setInterval> | undefined;
      let pendingRenewal: Promise<void> | null = null;
      let autoRenew = true;
      let stoppedResolve!: () => void;
      let stoppedReject!: (error: unknown) => void;
      const stopped = new Promise<void>((resolve, reject) => {stoppedResolve = resolve; stoppedReject = reject;});
      void stopped.catch(() => {});
      function closeScope() {if (!scopeClosed) {scopeClosed = true; scope.close();}}
      function stopSource() {
        if (!stopPromise) stopPromise = Promise.resolve().then(() => process?.stop());
        return stopPromise;
      }
      function stop(value: StopReason) {
        if (reason) return;
        reason = value; closeScope(); abort.abort();
        if (process) void stopSource().then(stoppedResolve, stoppedReject);
        else stoppedResolve();
      }
      cancelActive = () => stop('CANCELLED');
      const stoppedResult = (): CollectionWorkerResult => ({state: 'STOPPED', reason: reason!, taskCompleted: false,
        ...(requestId ? {requestId} : {}), ...(recoveryKey ? {recoveryKey} : {})});
      let validInput = false;
      try {
        const start = executionOperationSchema.parse(input.start);
        const receipt = parseExecutionReceipt(input.startReceipt, start);
        const strategy = strategyViewSchema.parse(input.strategy);
        const configuration=strategy.snapshot.configuration;
        const approvedMode=configuration.mode==='once' && configuration.schedule===null || input.allowMonitor===true &&
          configuration.mode==='monitor' && configuration.schedule?.policyVersion===1;
        if (start.operation !== 'START' || receipt.operation !== 'START' || !approvedMode ||
            strategy.state !== 'CONFIRMED' || !strategy.is_current || !strategy.profile_current ||
            strategy.revoked_at !== null || strategy.confirmed_at === null ||
            strategy.profile_version_id !== start.profile_version_id || strategy.strategy_version_id !== start.strategy_version_id ||
            strategy.snapshot.profile_version_id !== start.profile_version_id || strategy.snapshot.strategy_version_id !== start.strategy_version_id ||
            strategy.configuration_sha256 !== start.configuration_sha256 ||
            createHash('sha256').update(canonical(strategy.snapshot)).digest('hex') !== start.configuration_sha256 ||
            start.device_id !== scope.device.deviceId || start.credential_version !== scope.device.credentialVersion ||
            input.platformMaxRecords!==undefined && (!Number.isInteger(input.platformMaxRecords) || input.platformMaxRecords<1 ||
              input.platformMaxRecords>strategy.snapshot.max_records || input.platformMaxRecords>100)) throw new Error();
        const index = receipt.platform_runs.findIndex(run => run.platform_run_id === input.platformRunId);
        const target = start.targets![index];
        if (index < 0 || !target || !strategy.snapshot.platforms.includes(target.platform)) throw new Error();
        validInput = true;
        if (!scope.session.isCurrent()) stop('SESSION_CHANGED');
        if (reason) return stoppedResult();
        const operation = (kind: 'CLAIM' | 'RENEW', lease?: Lease) => executionOperationSchema.parse({
          schema_version: 'execution-runtime-v1', request_id: randomUUID(), operation: kind,
          device_id: start.device_id, credential_version: start.credential_version,
          task_id: receipt.task_id, platform_run_id: input.platformRunId,
          ...(lease ? {lease_id: lease.lease_id, execution_generation: lease.execution_generation} : {}),
        });
        let leaseDeadline = 0;
        const anchorWall = Date.now(), anchorMono = performance.now();
        let taskDeadline = Infinity;
        let renewAt = 0;
        let lease: Lease;
        async function acquire(request: ExecutionOperation): Promise<Lease | null> {
          requestId = request.request_id;
          // One wall-to-monotonic anchor for the whole run, including renewals.
          // Charge network wait and never extend the original task deadline.
          const sentMono = performance.now();
          let result;
          try {result = await execution.submit(scope.session, request);} catch {return null;}
          if (!scope.session.isCurrent()) stop('SESSION_CHANGED');
          if (reason || result.state !== 'RECORDED') return null;
          let parsed;
          try {parsed = parseExecutionReceipt(result.receipt, request);} catch {return null;}
          if ((parsed.operation !== 'CLAIM' && parsed.operation !== 'RENEW') || parsed.run_id !== receipt.run_id) return null;
          taskDeadline = Math.min(taskDeadline, anchorMono + Date.parse(parsed.deadline_at) - anchorWall);
          leaseDeadline = Math.min(anchorMono + Date.parse(parsed.lease_expires_at) - anchorWall,
            taskDeadline, sentMono + 120_000);
          if (!Number.isFinite(leaseDeadline) || performance.now() >= leaseDeadline) return null;
          renewAt = sentMono + Math.min(60_000, (leaseDeadline - sentMono) / 2);
          requestId = undefined;
          return parsed;
        }
        const claimed = await acquire(operation('CLAIM'));
        if (reason) return stoppedResult();
        if (!claimed) return {state: 'LEASE_UNKNOWN', requestId: requestId!, taskCompleted: false};
        lease = claimed;
        const maxRecords = input.platformMaxRecords??Math.min(strategy.snapshot.max_records, 100);
        process = driver.start({snapshot: structuredClone(strategy.snapshot), target: structuredClone(target),
          lease: structuredClone(lease), maxRecords, signal: abort.signal});
        timer = setInterval(() => {
          if (!scope.session.isCurrent()) stop('SESSION_CHANGED');
          if (performance.now() >= leaseDeadline) stop('LEASE_EXPIRED');
          if (reason || !autoRenew || pendingRenewal || performance.now() < renewAt) return;
          pendingRenewal = (async () => {
            const renewed = await acquire(operation('RENEW', lease));
            if (!renewed) stop('LEASE_UNKNOWN'); else lease = renewed;
          })().catch(() => stop('LEASE_UNKNOWN')).finally(() => {pendingRenewal = null;});
        }, 100);
        const outcome = await Promise.race([process.completed.then(records => ({records})), stopped.then(() => null)]);
        if (!outcome || reason) return stoppedResult();
        // Source collection has ended. Keep deadline/session monitoring, but no
        // timer renewal may race upload budget accounting or the FINISH journal.
        autoRenew = false;
        // Completed output is consumed only after its writer/browser has stopped.
        await stopSource();
        if (pendingRenewal) await Promise.race([pendingRenewal, stopped]);
        if (!scope.session.isCurrent()) stop('SESSION_CHANGED');
        if (performance.now() >= leaseDeadline) stop('LEASE_EXPIRED');
        if (reason) return stoppedResult();
        if (!Array.isArray(outcome.records) || outcome.records.length > maxRecords) throw new Error();
        // Renew at most once before upload if less than a normal minute remains.
        // After upload even a full record budget must proceed directly to FINISH.
        if (leaseDeadline - performance.now() < 60_000) {
          const renewed = await Promise.race([acquire(operation('RENEW', lease)), stopped.then(() => null)]);
          if (reason) return stoppedResult();
          if (!renewed) {stop('LEASE_UNKNOWN'); return stoppedResult();}
          lease = renewed;
        }
        const batch: CandidateSubmission = candidateSubmissionSchema.parse({schema_version: 'candidate-upload-v1', request_id: randomUUID(),
          platform: target.platform, profile_version_id: start.profile_version_id, strategy_version_id: start.strategy_version_id,
          execution: {device_id: start.device_id, credential_version: start.credential_version, task_id: receipt.task_id,
            run_id: receipt.run_id, platform_run_id: input.platformRunId, lease_id: lease.lease_id, execution_generation: lease.execution_generation,
            access_mode: target.access_mode, connection_id: target.connection_id, connection_version: target.connection_version}, records: outcome.records});
        recoveryKey = {platformRunId: input.platformRunId, requestId: batch.request_id};
        const uploaded = await Promise.race([
          candidates.submit(scope.session, batch).catch(() => null), stopped.then(() => null)]);
        if (!scope.session.isCurrent()) stop('SESSION_CHANGED');
        if (performance.now() >= leaseDeadline) stop('LEASE_EXPIRED');
        if (reason) return stoppedResult();
        if (uploaded?.state !== 'RECORDED') return {state: 'UPLOAD_UNKNOWN', recoveryKey, taskCompleted: false};
        const finish = executionOperationSchema.parse({schema_version: 'execution-runtime-v1', request_id: randomUUID(),
          operation: 'FINISH', device_id: start.device_id, credential_version: start.credential_version,
          task_id: receipt.task_id, platform_run_id: input.platformRunId, lease_id: lease.lease_id,
          execution_generation: lease.execution_generation, upload_request_id: batch.request_id});
        requestId = finish.request_id;
        const finished = await Promise.race([
          execution.submit(scope.session, finish).catch(() => null), stopped.then(() => null)]);
        if (!scope.session.isCurrent()) stop('SESSION_CHANGED');
        if (performance.now() >= leaseDeadline) stop('LEASE_EXPIRED');
        if (reason) return stoppedResult();
        const unknown: CollectionWorkerResult = {state: 'FINISH_UNKNOWN', requestId, recoveryKey, taskCompleted: false};
        if (finished?.state !== 'RECORDED') return unknown;
        let terminal;
        try {terminal = parseExecutionReceipt(finished.receipt, finish);} catch {return unknown;}
        if (terminal.operation !== 'FINISH' || terminal.run_id !== receipt.run_id) return unknown;
        return {state: 'COMPLETED', requestId, recoveryKey,
          taskCompleted: terminal.status === 'SUCCEEDED' && terminal.stop_confirmed};
      } catch {
        if (reason) return stoppedResult();
        return {state: 'FAILED', error: validInput ? 'COLLECTION_WORKER_FAILED' : 'COLLECTION_WORKER_INVALID_INPUT',
          taskCompleted: false, ...(recoveryKey ? {recoveryKey} : {})};
      } finally {
        if (timer) clearInterval(timer);
        abort.abort();
        try {if (process) await stopSource();}
        catch {closeScope(); cancelActive = null; return {state: 'FAILED', error: 'SOURCE_STOP_FAILED', taskCompleted: false,
          ...(recoveryKey ? {recoveryKey} : {})};}
        closeScope(); cancelActive = null;
      }
    },
  };
}
