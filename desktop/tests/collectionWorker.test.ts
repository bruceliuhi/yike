import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import * as workerModule from '../src/main/collectionWorker';
import {executionOperationSchema} from '../src/shared/executionOperation';
import {createHash} from 'node:crypto';

const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
function canonical(v: any): string {return Array.isArray(v) ? '[' + v.map(canonical).join(',') + ']' : v && typeof v === 'object'
  ? '{' + Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + canonical(v[k])).join(',') + '}' : JSON.stringify(v);}
function deferred<T>() {let resolve!: (value: T) => void; const promise = new Promise<T>(r => {resolve = r;}); return {promise, resolve};}
function fixture() {
  const output = deferred<unknown[]>(); let current = true;
  const start = executionOperationSchema.parse({schema_version: 'execution-runtime-v1', operation: 'START', request_id: id(1),
    device_id: id(2), credential_version: 1, profile_version_id: id(3), strategy_version_id: id(4), configuration_sha256: 'a'.repeat(64),
    targets: [{platform: 'BILIBILI', access_mode: 'PLATFORM_ACCOUNT', connection_id: id(5), connection_version: 1}]});
  const receipt = {schema_version: 'execution-runtime-v1', operation: 'START', request_id: id(1), task_id: id(6), run_id: id(7),
    status: 'PENDING', stop_confirmed: false, platform_runs: [{platform_run_id: id(8), platform: 'BILIBILI', status: 'PENDING'}]};
  const configuration = {schema_version: 'research-strategy-v1', name: '真实原文', source: 'search', keywords: ['展台'], exclusions: [],
    links: [], mode: 'once', schedule: null, research: null};
  const strategy = {schema_version: 'strategy-confirmation-v1', strategy_version_id: id(4), draft_id: id(10), draft_revision: 1,
    profile_version_id: id(3), profile_sha256: 'b'.repeat(64), configuration_sha256: 'a'.repeat(64), state: 'CONFIRMED',
    snapshot: {profile_version_id: id(3), strategy_version_id: id(4), configuration, platforms: ['BILIBILI'], max_records: 50, max_runtime_seconds: 600},
    created_at: '2026-09-10T00:00:00Z', confirmed_at: '2026-09-10T00:00:00Z', revoked_at: null, is_current: true, profile_current: true};
  start.configuration_sha256 = strategy.configuration_sha256 = createHash('sha256').update(canonical(strategy.snapshot)).digest('hex');
  const scope = {session: {userId: 'owner', sessionId: id(20), isCurrent: () => current}, device: {deviceId: id(2), credentialVersion: 1},
    transport: {requestExecution: vi.fn(), requestCandidate: vi.fn()}, close: vi.fn(() => {current = false;})};
  const execution = {submit: vi.fn(async (_session, request): Promise<any> => request.operation === 'FINISH'
    ? {state: 'RECORDED', receipt: finishReceipt(request)} : ({state: 'RECORDED', receipt: {
    schema_version: 'execution-runtime-v1', request_id: request.request_id, operation: request.operation, task_id: id(6), run_id: id(7),
    platform_run_id: id(8), status: 'RUNNING', stop_confirmed: false, lease_id: id(9), execution_generation: 1,
    lease_expires_at: new Date(Date.now() + 120_000).toISOString(), deadline_at: new Date(Date.now() + 600_000).toISOString()}}))};
  const candidates = {submit: vi.fn(async (_session: unknown, _batch: unknown) => ({state: 'UNKNOWN', key: {platformRunId: id(8), requestId: 'original'}}))};
  const stopped = vi.fn(async () => {});
  const driver = {start: vi.fn((_input: any) => ({completed: output.promise, stop: stopped}))};
  const instance = (workerModule as any).createCollectionWorker({execution, candidates, driver});
  return {instance, scope, execution, candidates, driver, stopped, output, strategy, start, receipt,
    run: () => instance.run({scope, start, startReceipt: receipt, strategy, platformRunId: id(8)}),
    expire: () => {current = false;}};
}
beforeEach(() => {vi.useFakeTimers(); vi.setSystemTime(new Date('2026-09-10T00:01:00Z'));});
afterEach(() => vi.useRealTimers());
async function tick(ms = 0) {await vi.advanceTimersByTimeAsync(ms);}
function finishReceipt(request: any) {return {schema_version: 'execution-runtime-v1', operation: 'FINISH',
  request_id: request.request_id, task_id: id(6), run_id: id(7), platform_run_id: id(8),
  lease_id: id(9), execution_generation: 1, upload_request_id: request.upload_request_id,
  records_used: 0, status: 'SUCCEEDED', stop_confirmed: true};}

it('claims before source, stops source before upload, preserves original execution tuple and unknown result', async () => {
  const f = fixture(); const done = f.run(); await tick();
  expect(f.execution.submit).toHaveBeenCalledTimes(1);
  expect(f.execution.submit.mock.calls[0][1]).toMatchObject({operation: 'CLAIM', task_id: id(6), platform_run_id: id(8)});
  expect(f.driver.start).toHaveBeenCalledTimes(1);
  f.output.resolve([]); await tick();
  const result = await done;
  expect(result).toMatchObject({state: 'UPLOAD_UNKNOWN', taskCompleted: false});
  expect(f.stopped).toHaveBeenCalledTimes(1);
  expect(f.candidates.submit).toHaveBeenCalledTimes(1);
  expect(f.candidates.submit.mock.calls[0][1]).toMatchObject({profile_version_id: id(3), strategy_version_id: id(4), platform: 'BILIBILI',
    execution: {device_id: id(2), task_id: id(6), run_id: id(7), platform_run_id: id(8), lease_id: id(9), execution_generation: 1,
      access_mode: 'PLATFORM_ACCOUNT', connection_id: id(5), connection_version: 1}, records: []});
  expect(f.scope.close).toHaveBeenCalledTimes(1);
});

it('renewal uses a new operation id and the same lease without repeating collection', async () => {
  const f = fixture(); const done = f.run(); await tick(); await tick(60_000);
  expect(f.execution.submit).toHaveBeenCalledTimes(2);
  const [claim, renew] = f.execution.submit.mock.calls.map(c => c[1]);
  expect(renew).toMatchObject({operation: 'RENEW', lease_id: id(9), execution_generation: 1});
  expect(renew.request_id).not.toBe(claim.request_id);
  expect(f.driver.start).toHaveBeenCalledTimes(1);
  f.instance.cancel(); await tick(); expect(await done).toMatchObject({state: 'STOPPED', reason: 'CANCELLED'});
});

it.each(['cancel', 'session', 'renew'])('stops and awaits driver on %s without uploading or restarting', async kind => {
  const f = fixture(); const stopping = deferred<void>(); f.stopped.mockImplementation(() => stopping.promise);
  const done = f.run(); await tick();
  if (kind === 'cancel') f.instance.cancel();
  if (kind === 'session') f.expire();
  if (kind === 'renew') {f.execution.submit.mockResolvedValueOnce({state: 'UNKNOWN', requestId: id(99)} as any); await tick(60_000);}
  await tick(200); let settled = false; void done.then(() => {settled = true;}); await tick();
  expect(f.stopped).toHaveBeenCalledTimes(1); expect(settled).toBe(false);
  stopping.resolve(); await tick(); expect(await done).toMatchObject({state: 'STOPPED', taskCompleted: false});
  expect(f.candidates.submit).not.toHaveBeenCalled(); expect(f.driver.start).toHaveBeenCalledTimes(1);
});

it('unknown claim preserves operation recovery id and never starts a source', async () => {
  const f = fixture(); f.execution.submit.mockImplementationOnce(async (_s, request) => ({state: 'UNKNOWN', requestId: request.request_id} as any));
  expect(await f.run()).toMatchObject({state: 'LEASE_UNKNOWN', requestId: expect.any(String), taskCompleted: false});
  expect(f.driver.start).not.toHaveBeenCalled(); expect(f.candidates.submit).not.toHaveBeenCalled();
});

it('rejects changed strategy/profile/device/run bindings before source or claim', async () => {
  const f = fixture(); f.strategy.profile_version_id = id(99);
  expect(await f.run()).toMatchObject({state: 'FAILED', error: 'COLLECTION_WORKER_INVALID_INPUT'});
  expect(f.execution.submit).not.toHaveBeenCalled(); expect(f.driver.start).not.toHaveBeenCalled();
});

it('oversized source output is not silently truncated into an apparent success', async () => {
  const f = fixture(); const done = f.run(); await tick(); f.output.resolve(Array(51).fill({})); await tick();
  expect(await done).toMatchObject({state: 'FAILED'}); expect(f.candidates.submit).not.toHaveBeenCalled();
});

it('cancel during pending upload invalidates the local scope immediately and keeps the original key', async () => {
  const f = fixture(); const sending = deferred<any>(); f.candidates.submit.mockImplementation(() => sending.promise);
  const done = f.run(); await tick(); f.output.resolve([]); await tick();
  f.instance.cancel();
  expect(f.scope.session.isCurrent()).toBe(false);
  sending.resolve({state: 'SESSION_CHANGED'}); await tick();
  expect(await done).toMatchObject({state: 'STOPPED', reason: 'CANCELLED', recoveryKey: {
    platformRunId: id(8), requestId: expect.any(String)}});
  expect(f.scope.close).toHaveBeenCalledTimes(1);
});

it('waits for source stop failure and does not claim a confirmed stop', async () => {
  const f = fixture(); f.stopped.mockRejectedValue(new Error('private driver error'));
  const done = f.run(); await tick(); f.instance.cancel(); await tick();
  expect(await done).toEqual({state: 'FAILED', error: 'SOURCE_STOP_FAILED', taskCompleted: false});
  expect(f.candidates.submit).not.toHaveBeenCalled();
});

it('late renew cannot keep the browser running past the prior lease expiry', async () => {
  const f = fixture(); const renew = deferred<any>(); const done = f.run(); await tick();
  f.execution.submit.mockImplementationOnce(() => renew.promise);
  await tick(120_100);
  expect(await done).toMatchObject({state: 'STOPPED', reason: 'LEASE_EXPIRED', requestId: expect.any(String)});
  expect(f.stopped).toHaveBeenCalledTimes(1); expect(f.candidates.submit).not.toHaveBeenCalled();
  renew.resolve({state: 'UNKNOWN', requestId: id(99)}); await tick();
  expect(f.driver.start).toHaveBeenCalledTimes(1);
});

it('changed configuration with an unchanged hash is rejected', async () => {
  const f = fixture(); f.strategy.snapshot.configuration.keywords = ['已被篡改'];
  expect(await f.run()).toMatchObject({state: 'FAILED', error: 'COLLECTION_WORKER_INVALID_INPUT'});
  expect(f.execution.submit).not.toHaveBeenCalled();
});

it('keeps the CLAIM recovery id on an invalid receipt', async () => {
  const f = fixture(); f.execution.submit.mockResolvedValueOnce({state: 'RECORDED', receipt: {}} as any);
  expect(await f.run()).toMatchObject({state: 'LEASE_UNKNOWN', requestId: expect.any(String)});
  expect(f.driver.start).not.toHaveBeenCalled();
});

it('normal AbortError keeps cancellation reason and awaits physical stop', async () => {
  const f = fixture(); const stopping = deferred<void>(); f.stopped.mockImplementation(() => stopping.promise);
  f.driver.start.mockImplementation(({signal}) => ({completed: new Promise((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(new Error('AbortError')), {once: true});
  }), stop: f.stopped}));
  const done = f.run(); await tick(); f.instance.cancel(); await tick();
  let settled = false; void done.then(() => {settled = true;}); await tick(); expect(settled).toBe(false);
  stopping.resolve(); await tick();
  expect(await done).toEqual({state: 'STOPPED', reason: 'CANCELLED', taskCompleted: false});
});

it('backward wall clock during renewal cannot extend the original task deadline', async () => {
  const f = fixture(); const serverDeadline = new Date(Date.now() + 90_000).toISOString();
  f.execution.submit.mockImplementation(async (_s, request) => ({state: 'RECORDED', receipt: {
    schema_version: 'execution-runtime-v1', request_id: request.request_id, operation: request.operation, task_id: id(6), run_id: id(7),
    platform_run_id: id(8), status: 'RUNNING', stop_confirmed: false, lease_id: id(9), execution_generation: 1,
    lease_expires_at: serverDeadline, deadline_at: serverDeadline}}));
  const done = f.run(); await tick(); await tick(44_000); vi.setSystemTime(Date.now() - 60_000);
  await tick(46_100);
  const stoppedAtDeadline = f.stopped.mock.calls.length;
  f.instance.cancel(); await tick(); await done;
  expect(stoppedAtDeadline).toBe(1);
});

it('does not silently execute deferred monitoring strategies as a one-shot collection', async () => {
  const f = fixture(); f.strategy.snapshot.configuration.mode = 'monitor';
  (f.strategy.snapshot.configuration as any).schedule = {kind: 'interval', times: [], interval: 1,
    start: '09:00', end: '18:00', timezone: 'Asia/Shanghai'};
  f.start.configuration_sha256 = f.strategy.configuration_sha256 = createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');
  const done = f.run(); await tick();
  const claimed = f.execution.submit.mock.calls.length;
  f.instance.cancel(); await tick(); const result = await done;
  expect(claimed).toBe(0);
  expect(result).toMatchObject({state: 'FAILED', error: 'COLLECTION_WORKER_INVALID_INPUT'});
});

it('executes one server-reserved monitor iteration only with main-only authorization', async () => {
  const f = fixture(); f.strategy.snapshot.configuration.mode = 'monitor';
  (f.strategy.snapshot.configuration as any).schedule = {kind: 'interval', times: [], interval: 1,
    start: '09:00', end: '18:00', timezone: 'Asia/Shanghai', policyVersion: 1};
  f.start.configuration_sha256 = f.strategy.configuration_sha256 = createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');
  const done=f.instance.run({scope:f.scope,start:f.start,startReceipt:f.receipt,strategy:f.strategy,platformRunId:id(8),allowMonitor:true});
  await tick(); expect(f.execution.submit.mock.calls[0][1]).toMatchObject({operation:'CLAIM'});
  f.instance.cancel();await tick();expect(await done).toMatchObject({state:'STOPPED'});
});

it('FINISH follows physical source stop and recorded upload with the exact original tuple', async () => {
  const f = fixture(); const physical = deferred<void>(); const upload = deferred<any>();
  f.stopped.mockImplementation(() => physical.promise); f.candidates.submit.mockImplementation(() => upload.promise);
  const done = f.run(); await tick(); f.output.resolve([]); await tick();
  expect(f.candidates.submit).not.toHaveBeenCalled(); expect(f.execution.submit).toHaveBeenCalledTimes(1);
  physical.resolve(); await tick(); expect(f.candidates.submit).toHaveBeenCalledTimes(1);
  expect(f.execution.submit).toHaveBeenCalledTimes(1);
  upload.resolve({state: 'RECORDED'}); await tick();
  const result = await done; const batch = f.candidates.submit.mock.calls[0][1] as any;
  expect(f.execution.submit).toHaveBeenCalledTimes(2);
  const finish = f.execution.submit.mock.calls[1][1];
  expect(finish).toMatchObject({operation: 'FINISH', task_id: id(6), platform_run_id: id(8),
    lease_id: id(9), execution_generation: 1, upload_request_id: batch.request_id});
  expect(result).toMatchObject({state: 'COMPLETED', taskCompleted: true, requestId: finish.request_id,
    recoveryKey: {platformRunId: id(8), requestId: batch.request_id}});
  expect(f.stopped).toHaveBeenCalledTimes(1);
});

it.each(['RUNNING', 'UNKNOWN', 'invalid', 'throw'])('FINISH %s never falsely marks task complete and retains both recovery ids', async kind => {
  const f = fixture(); f.candidates.submit.mockResolvedValue({state: 'RECORDED'} as any);
  const done = f.run(); await tick();
  f.execution.submit.mockImplementationOnce(async (_s, request) => {
    if (kind === 'throw') throw new Error('private');
    if (kind === 'UNKNOWN') return {state: 'UNKNOWN', requestId: request.request_id};
    const receipt = finishReceipt(request);
    if (kind === 'RUNNING') {receipt.status = 'RUNNING'; receipt.stop_confirmed = false;}
    if (kind === 'invalid') receipt.run_id = id(99);
    return {state: 'RECORDED', receipt};
  });
  f.output.resolve([]); await tick();
  const result = await done; const finish = f.execution.submit.mock.calls[1]?.[1];
  expect(result).toMatchObject({state: kind === 'RUNNING' ? 'COMPLETED' : 'FINISH_UNKNOWN',
    taskCompleted: false, requestId: finish?.request_id, recoveryKey: {platformRunId: id(8), requestId: expect.any(String)}});
});

it('drains an existing renewal then disables automatic renew during upload and FINISH', async () => {
  const f = fixture(); const renewal = deferred<any>(); const upload = deferred<any>();
  f.candidates.submit.mockImplementation(() => upload.promise);
  const done = f.run(); await tick(); f.execution.submit.mockImplementationOnce(() => renewal.promise);
  await tick(60_000); f.output.resolve([]); await tick(); expect(f.candidates.submit).not.toHaveBeenCalled();
  const request = f.execution.submit.mock.calls[1][1];
  renewal.resolve({state: 'RECORDED', receipt: {schema_version: 'execution-runtime-v1', operation: 'RENEW',
    request_id: request.request_id, task_id: id(6), run_id: id(7), platform_run_id: id(8), status: 'RUNNING', stop_confirmed: false,
    lease_id: id(9), execution_generation: 1, lease_expires_at: new Date(Date.now() + 120_000).toISOString(),
    deadline_at: new Date(Date.now() + 540_000).toISOString()}});
  await tick(); expect(f.candidates.submit).toHaveBeenCalledTimes(1);
  await tick(61_000); expect(f.execution.submit).toHaveBeenCalledTimes(2);
  upload.resolve({state: 'RECORDED'}); await tick();
  expect((await done).state).toBe('COMPLETED');
  expect(f.execution.submit.mock.calls.map(c => c[1].operation)).toEqual(['CLAIM', 'RENEW', 'FINISH']);
});

it.each(['upload', 'finish'])('deadline still closes the scope during pending %s without a late success', async phase => {
  const f = fixture(); const pending = deferred<any>();
  f.candidates.submit.mockImplementation(() => phase === 'upload' ? pending.promise : Promise.resolve({state: 'RECORDED'} as any));
  const done = f.run(); await tick();
  if (phase === 'finish') f.execution.submit.mockImplementationOnce(() => pending.promise);
  f.output.resolve([]); await tick(); await tick(120_100);
  expect(await done).toMatchObject({state: 'STOPPED', reason: 'LEASE_EXPIRED', taskCompleted: false,
    recoveryKey: {platformRunId: id(8), requestId: expect.any(String)}});
  expect(f.scope.close).toHaveBeenCalledTimes(1);
  pending.resolve({state: 'UNKNOWN'}); await tick(); expect(f.driver.start).toHaveBeenCalledTimes(1);
});

it('renews a short remaining lease exactly once before upload, never after it', async () => {
  const f = fixture(); const submit = f.execution.submit.getMockImplementation()!;
  f.execution.submit.mockImplementationOnce(async (session, request) => {
    const response = await submit(session, request);
    response.receipt.lease_expires_at = new Date(Date.now() + 20_000).toISOString(); return response;
  });
  f.candidates.submit.mockResolvedValue({state: 'RECORDED'} as any);
  const done = f.run(); await tick(); f.output.resolve([]); await tick();
  expect(await done).toMatchObject({state: 'COMPLETED', taskCompleted: true});
  expect(f.execution.submit.mock.calls.map(c => c[1].operation)).toEqual(['CLAIM', 'RENEW', 'FINISH']);
});

it.each(['cancel', 'session'])('pending FINISH preserves its request id on %s and never restarts', async kind => {
  const f = fixture(); const pending = deferred<any>(); f.candidates.submit.mockResolvedValue({state: 'RECORDED'} as any);
  const done = f.run(); await tick(); f.execution.submit.mockImplementationOnce(() => pending.promise);
  f.output.resolve([]); await tick(); const finish = f.execution.submit.mock.calls[1][1];
  if (kind === 'cancel') f.instance.cancel(); else f.expire();
  await tick(100);
  expect(await done).toMatchObject({state: 'STOPPED', reason: kind === 'cancel' ? 'CANCELLED' : 'SESSION_CHANGED',
    taskCompleted: false, requestId: finish.request_id, recoveryKey: {platformRunId: id(8), requestId: expect.any(String)}});
  pending.resolve({state: 'RECORDED', receipt: finishReceipt(finish)}); await tick();
  expect(f.execution.submit).toHaveBeenCalledTimes(2); expect(f.driver.start).toHaveBeenCalledTimes(1);
});
