import {expect, it, vi} from 'vitest';
import {createHash, createCipheriv, createDecipheriv, createPublicKey, randomBytes, verify} from 'node:crypto';
import {mkdtemp, readFile, readdir, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {createForegroundCollectionController} from '../src/main/foregroundCollectionController';
import {createExecutionJournal} from '../src/main/executionJournal';
import {createExecutionSession} from '../src/main/executionSession';
import {createCandidateJournal} from '../src/main/candidateJournal';
import {createCandidateSession} from '../src/main/candidateSession';
import {createDeviceKeyVault} from '../src/main/deviceKeyVault';
import type {DeviceWorkerScope} from '../src/main/deviceIdentityController';
import type {ApiResult} from '../src/shared/contracts';
import type {CandidateSubmission} from '../src/shared/candidateSubmission';
import type {CollectionDriver} from '../src/main/collectionWorker';
import {id, recoveryReceipt} from './candidateRecoveryFixtures';

function canonical(value: any): string {return Array.isArray(value) ? '[' + value.map(canonical).join(',') + ']' :
  value && typeof value === 'object' ? '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}' : JSON.stringify(value);}
function deferred<T>() {let resolve!: (value: T) => void; const promise = new Promise<T>(r => {resolve = r;}); return {promise, resolve};}
const origin = 'https://fixture.invalid';
const record = {kind: 'COMMENT', external_source_id: '66c01234abcdef0123456789', external_comment_id: '66c11234abcdef0123456789',
  public_url: 'https://www.xiaohongshu.com/explore/66c01234abcdef0123456789', title: null, author_public_id: null,
  body: '  原文 é😀\n\t ', published_at: null, observed_at: '2026-09-10T00:00:00Z', parent: null,
  collector_version: 'controlled-source-v1', normalizer_version: 'normalizer-v1', query: '设计'};

async function fixture({loseUpload = false, holdSource = false} = {}) {
  const directory = await mkdtemp(path.join(tmpdir(), 'yike-foreground-integration-'));
  const secret = randomBytes(32);
  // Test-only authenticated protection; the production vault/journal disk formats and fsync are real.
  const protection = {isEncryptionAvailable: () => true,
    encryptString(value: string) {const nonce = randomBytes(12), cipher = createCipheriv('aes-256-gcm', secret, nonce);
      const body = Buffer.concat([cipher.update(value, 'utf8'), cipher.final()]); return Buffer.concat([nonce, cipher.getAuthTag(), body]);},
    decryptString(value: Buffer) {const cipher = createDecipheriv('aes-256-gcm', secret, value.subarray(0, 12));
      cipher.setAuthTag(value.subarray(12, 28)); return Buffer.concat([cipher.update(value.subarray(28)), cipher.final()]).toString('utf8');}};
  const journalScope = {serviceOrigin: origin, userId: 'owner'};
  const keyScope = {...journalScope, deviceId: id(2)};
  const vault = () => createDeviceKeyVault({directory: path.join(directory, 'keys'), protection});
  const material = await vault().getOrCreate(keyScope);
  const publicKey = createPublicKey(material.privateKey);
  const executionJournal = () => createExecutionJournal({directory: path.join(directory, 'execution'), protection});
  const candidateJournal = () => createCandidateJournal({directory: path.join(directory, 'candidate'), protection});
  const events: string[] = [];
  const source = deferred<unknown[]>(), sourceStarted = deferred<void>(), physical = deferred<void>();
  if (!holdSource) {source.resolve([structuredClone(record)]); physical.resolve();}
  let epoch = 1, serverStatus = 'PENDING', recordsUsed = 0;
  const receipts = new Map<string, unknown>(), executionPayloads = new Map<string, string>(), candidatePayloads = new Map<string, string>();
  let committed: CandidateSubmission | null = null;
  const snapshot = {profile_version_id: id(3), strategy_version_id: id(4), configuration: {schema_version: 'research-strategy-v1',
    name: '原文', source: 'search', keywords: ['设计'], exclusions: [], links: [], mode: 'once', schedule: null, research: null},
    platforms: ['XIAOHONGSHU'], max_records: 1, max_runtime_seconds: 600};
  const configurationSha256 = createHash('sha256').update(canonical(snapshot)).digest('hex');
  const strategy = {schema_version: 'strategy-confirmation-v1', strategy_version_id: id(4), profile_version_id: id(3), draft_id: id(10),
    draft_revision: 1, profile_sha256: 'b'.repeat(64), configuration_sha256: configurationSha256, snapshot, state: 'CONFIRMED',
    created_at: '2026-09-10T00:00:00Z', confirmed_at: '2026-09-10T00:00:00Z', revoked_at: null, is_current: true, profile_current: true};
  const command = {action: 'START', humanConfirmed: true, requestId: id(1), profileVersionId: id(3), strategyVersionId: id(4), configurationSha256,
    targets: [{platform: 'XIAOHONGSHU', access_mode: 'PLATFORM_ACCOUNT', connection_id: id(5), connection_version: 2}]};
  const okay = (data: unknown): ApiResult => ({ok: true, status: 200, data});
  const missing = (): ApiResult => ({ok: false, status: 404, error: 'request_not_found'});
  const deadline = new Date(Date.now() + 600_000).toISOString();
  const task = () => ({task_id: id(6), run_id: id(7), status: serverStatus, stop_confirmed: serverStatus === 'SUCCEEDED',
    profile_version_id: id(3), strategy_version_id: id(4), max_records: 1, records_used: recordsUsed, deadline_at: deadline,
    platform_runs: [{platform_run_id: id(8), platform: 'XIAOHONGSHU', status: serverStatus, execution_generation: serverStatus === 'PENDING' ? 0 : 1, records_used: recordsUsed}]});
  // Fixed HTTP-operation fixture: no fetch, sockets, platform login or actual browser exists here.
  const requestExecution = vi.fn(async (input: any): Promise<ApiResult> => {
    if (input.operation === 'execution.support') return okay({schema_version: 'foreground-collection-support-v1', mode: 'xhs-foreground-v1'});
    if (input.operation === 'execution.task') return okay(task());
    if (input.operation === 'execution.receipt') {events.push('execution.receipt'); return receipts.has(input.payload.request_id) ? okay(receipts.get(input.payload.request_id)) : missing();}
    if (input.operation === 'execution.prepare') {
      const request = input.payload.request;
      // Reopen and read real durable journal before either signing preparation or apply.
      expect(await executionJournal().read(journalScope, request.request_id)).toEqual(request);
      events.push('persisted:' + request.operation);
      const signing_payload = canonical({protocol: 'yike-execution-operation-v1', tenant_id: 'tenant', user_id: 'owner',
        session_digest: 'a'.repeat(64), operation: request});
      executionPayloads.set(request.request_id, signing_payload);
      return okay({request_id: request.request_id, device_id: request.device_id, credential_version: request.credential_version,
        request_sha256: createHash('sha256').update(canonical(request)).digest('hex'), signing_payload});
    }
    expect(input.operation).toBe('execution.apply');
    const {request, signature} = input.payload;
    expect(verify(null, Buffer.from(executionPayloads.get(request.request_id)!), publicKey, Buffer.from(signature, 'base64url'))).toBe(true);
    events.push(request.operation);
    const envelope = {schema_version: 'execution-runtime-v1', request_id: request.request_id, operation: request.operation, task_id: id(6), run_id: id(7)};
    let receipt: unknown;
    if (request.operation === 'START') receipt = {...envelope, status: 'PENDING', stop_confirmed: false,
      platform_runs: [{platform_run_id: id(8), platform: 'XIAOHONGSHU', status: 'PENDING'}]};
    else if (request.operation === 'FINISH') {
      expect(events).toContain('source-stopped'); expect(committed).not.toBeNull();
      expect(request.upload_request_id).toBe(committed!.request_id);
      serverStatus = 'SUCCEEDED'; receipt = {...envelope, status: 'SUCCEEDED', stop_confirmed: true,
        platform_run_id: id(8), lease_id: id(9), execution_generation: 1, upload_request_id: request.upload_request_id, records_used: recordsUsed};
    } else {
      expect(['CLAIM', 'RENEW']).toContain(request.operation); serverStatus = 'RUNNING';
      receipt = {...envelope, platform_run_id: id(8), status: 'RUNNING', stop_confirmed: false, lease_id: id(9), execution_generation: 1,
        lease_expires_at: new Date(Date.now() + 120_000).toISOString(), deadline_at: deadline};
    }
    receipts.set(request.request_id, receipt); return okay(receipt);
  });
  const requestCandidate = vi.fn(async (input: any): Promise<ApiResult> => {
    if (input.operation === 'candidate.receipt') {
      events.push('candidate.receipt');
      expect(input.payload).toEqual({platform_run_id: id(8), request_id: committed!.request_id});
      return committed ? okay(recoveryReceipt(committed)) : missing();
    }
    if (input.operation === 'candidate.prepare') {
      const batch = input.payload.batch as CandidateSubmission;
      expect(events).toContain('source-stopped');
      expect(await candidateJournal().read(journalScope, {platformRunId: id(8), requestId: batch.request_id})).toEqual(batch);
      expect(batch.records).toEqual([record]); events.push('persisted:batch');
      const {request_id, ...fingerprinted} = batch;
      const batch_fingerprint = createHash('sha256').update(canonical(fingerprinted)).digest('hex');
      const signing_payload = canonical({protocol: 'yike-candidate-submission-v1', tenant_id: 'tenant', user_id: 'owner',
        session_digest: 'a'.repeat(64), request_id, batch_fingerprint});
      candidatePayloads.set(request_id, signing_payload);
      return okay({request_id, device_id: id(2), credential_version: 1, batch_fingerprint, signing_payload});
    }
    expect(input.operation).toBe('candidate.apply');
    const {batch, signature} = input.payload;
    expect(verify(null, Buffer.from(candidatePayloads.get(batch.request_id)!), publicKey, Buffer.from(signature, 'base64url'))).toBe(true);
    events.push('candidate.apply'); committed = structuredClone(batch); recordsUsed = batch.records.length;
    if (loseUpload) throw new Error('controlled response loss after commit');
    return okay(recoveryReceipt(batch));
  });
  const identity = {
    getStatus: () => ({state: 'READY' as const, deviceId: id(2), credentialVersion: 1}),
    requestApi: vi.fn(async (): Promise<ApiResult> => okay(strategy)),
    openWorkerScope: vi.fn(async () => {
      const openedEpoch = epoch; let closed = false;
      const scope: DeviceWorkerScope = {device: {deviceId: id(2), credentialVersion: 1},
        session: {userId: 'owner', sessionId: id(20 + epoch), isCurrent: () => !closed && openedEpoch === epoch},
        transport: {requestExecution, requestCandidate, requestConnection: async () => missing()}, close() {closed = true;}};
      return {ok: true as const, scope};
    }),
  };
  const driver: CollectionDriver = {start: vi.fn(input => {
    expect(events).toContain('CLAIM'); expect(input.maxRecords).toBe(1); sourceStarted.resolve(); events.push('source-started');
    return {completed: source.promise, async stop() {events.push('source-stop-requested'); await physical.promise; events.push('source-stopped');}};
  })};
  const controllers: ReturnType<typeof createForegroundCollectionController>[] = [];
  function controller() {
    const result = createForegroundCollectionController({serviceOrigin: origin, identity, store: {read: async () => null},
      executionJournal: executionJournal(), candidateJournal: candidateJournal(),
      configuration: {pythonExecutable: 'C:/fixed/python.exe', projectRoot: 'C:/fixed/project', runtimePath: 'C:/fixed/runtime', profileRoot: 'C:/fixed/profiles', outputRoot: 'C:/fixed/output'},
      probe: async () => true, resolveAccount: async () => ({profileId: id(30), accountPublicId: '66c01234abcdef0123456789'}),
      driverFactory: options => {expect(options.binding.expectedAccountPublicId).toBe('66c01234abcdef0123456789'); return driver;},
      sessions: scope => ({execution: createExecutionSession({serviceOrigin: origin, journal: executionJournal(), vault: vault(), transport: scope.transport}),
        candidates: createCandidateSession({serviceOrigin: origin, journal: candidateJournal(), vault: vault(), transport: scope.transport})})});
    controllers.push(result); return result;
  }
  async function idle(controller: ReturnType<typeof createForegroundCollectionController>) {
    let result: Awaited<ReturnType<typeof controller.execute>>;
    await vi.waitFor(async () => {result = await controller.execute({action: 'STATUS', taskId: id(6)});
      expect(result).toMatchObject({state: 'STATUS'}); expect((result as any).localState).not.toBe('COLLECTING');}, {timeout: 3000, interval: 10});
    // A STATUS begun before commit can finish after the local worker. Re-read
    // after quiescence to compare one stable server/local state, not that race.
    return controller.execute({action: 'STATUS', taskId: id(6)});
  }
  return {controller, idle, command, events, driver, requestExecution, requestCandidate, sourceStarted, physical,
    invalidate: () => {epoch++;}, candidateJournal, executionJournal, journalScope, directory,
    committed: () => committed,
    async cleanup() {
      physical.resolve(); source.resolve([]); for (const c of controllers) await c.shutdown();
      const target = path.resolve(directory);
      if (path.dirname(target) !== path.resolve(tmpdir()) || !path.basename(target).startsWith('yike-foreground-integration-')) throw new Error('unsafe fixture cleanup');
      await rm(target, {recursive: true, force: true});
    }};
}

it('real controller/session/vault/journals complete START → CLAIM → physical stop → original upload → FINISH', async () => {
  const f = await fixture();
  try {
    const controller = f.controller(); expect(await controller.start(f.command)).toMatchObject({state: 'RECORDED'});
    expect(await f.idle(controller)).toMatchObject({state: 'STATUS', localState: 'COMPLETED', serverStatus: 'SUCCEEDED', stopConfirmed: true, recordsUsed: 1, recoverable: false});
    expect(f.events).toEqual(['persisted:START', 'START', 'persisted:CLAIM', 'CLAIM', 'source-started', 'source-stop-requested',
      'source-stopped', 'persisted:batch', 'candidate.apply', 'persisted:FINISH', 'FINISH']);
    const batch = f.committed()!;
    expect(await f.candidateJournal().read(f.journalScope, {platformRunId: id(8), requestId: batch.request_id})).toEqual(batch);
    const files = await readdir(path.join(f.directory, 'candidate'));
    expect(files).toHaveLength(1); expect((await readFile(path.join(f.directory, 'candidate', files[0]))).includes(Buffer.from(record.body))).toBe(false);
    expect(f.driver.start).toHaveBeenCalledTimes(1);
  } finally {await f.cleanup();}
});

it('lost upload receipt recovers its original key after controller reconstruction without re-CLAIM or source restart', async () => {
  const f = await fixture({loseUpload: true});
  try {
    const first = f.controller(); await first.start(f.command);
    expect(await f.idle(first)).toMatchObject({localState: 'UPLOAD_UNKNOWN', serverStatus: 'RUNNING', recordsUsed: 1, recoverable: true});
    const batch = f.committed()!; const before = structuredClone(batch);
    await first.shutdown(); const reopened = f.controller();
    // A RUNNING generation cannot become a fresh START after reconstruction.
    expect(await reopened.start(f.command)).toMatchObject({state: 'SERVICE_UNAVAILABLE'});
    expect(f.driver.start).toHaveBeenCalledTimes(1); expect(f.events.filter(e => e === 'CLAIM')).toHaveLength(1);
    expect(await reopened.execute({action: 'RECOVER', taskId: id(6), humanConfirmed: true, retry: false})).toMatchObject({localState: 'COMPLETED', serverStatus: 'SUCCEEDED', stopConfirmed: true});
    expect(f.events.filter(e => e === 'candidate.apply')).toHaveLength(1);
    expect(f.events.filter(e => e === 'candidate.receipt')).toHaveLength(1);
    expect(f.events.filter(e => e === 'FINISH')).toHaveLength(1);
    expect(f.committed()).toEqual(before); expect(f.driver.start).toHaveBeenCalledTimes(1);
  } finally {await f.cleanup();}
});

it('session epoch change closes and awaits the real worker source without upload or FINISH', async () => {
  const f = await fixture({holdSource: true});
  try {
    const controller = f.controller(); await controller.start(f.command); await f.sourceStarted.promise;
    f.invalidate(); await vi.waitFor(() => expect(f.events).toContain('source-stop-requested'));
    let stopped = false; const closing = controller.shutdown().then(() => {stopped = true;});
    await new Promise(resolve => setTimeout(resolve, 10)); expect(stopped).toBe(false);
    f.physical.resolve(); await closing; expect(stopped).toBe(true);
    expect(f.events).toContain('source-stopped'); expect(f.events).not.toContain('candidate.apply'); expect(f.events).not.toContain('FINISH');
    expect(await f.candidateJournal().list(f.journalScope)).toEqual([]);
    expect(f.driver.start).toHaveBeenCalledTimes(1);
  } finally {await f.cleanup();}
});
