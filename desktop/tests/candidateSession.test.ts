import {createHash, generateKeyPairSync} from 'node:crypto';
import {expect, it, vi} from 'vitest';
import {createCandidateSession} from '../src/main/candidateSession';
import type {CandidateSubmission} from '../src/shared/candidateSubmission';
import type {ApiResult} from '../src/shared/contracts';
import {id, recoveryBatch, recoveryReceipt} from './candidateRecoveryFixtures';
function canonical(v: any): string {
  return Array.isArray(v) ? '[' + v.map(canonical).join(',') + ']' : v !== null && typeof v === 'object'
    ? '{' + Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + canonical(v[k])).join(',') + '}' : JSON.stringify(v);
}
function fixture() {
  const origin = 'https://pilot.example'; let current = true; let saved: CandidateSubmission | null = null;
  const batch = recoveryBatch(), receipt = recoveryReceipt(batch);
  const events: string[] = [];
  const session = {userId: 'user😀', sessionId: id(30), isCurrent: () => current};
  const pair = generateKeyPairSync('ed25519');
  const key = {scope: {serviceOrigin: origin, userId: session.userId, deviceId: batch.execution.device_id},
    privateKey: pair.privateKey.export({format: 'pem', type: 'pkcs8'}).toString(), publicKey: pair.publicKey.export({format: 'jwk'}).x!};
  const journal = {
    persist: vi.fn(async (_scope: any, value: CandidateSubmission) => {
      events.push('persist'); const created = saved === null;
      if (saved && canonical(saved) !== canonical(value)) throw new Error('conflict');
      saved = structuredClone(value); return {batch: structuredClone(saved), created};
    }),
    read: vi.fn(async () => {events.push('read'); return saved && structuredClone(saved);}),
    list: vi.fn(async () => {events.push('list'); return saved ? [{platformRunId: saved.execution.platform_run_id, requestId: saved.request_id}] : [];}),
  };
  const vault = {read: vi.fn(async () => {events.push('key'); return key;})};
  const transport = {requestCandidate: vi.fn(async (input: any): Promise<ApiResult> => {
    events.push(input.operation);
    if (input.operation === 'candidate.prepare') {
      const b = input.payload.batch; const {request_id, ...hashed} = b;
      const fingerprint = createHash('sha256').update(canonical(hashed)).digest('hex');
      return {ok: true, status: 200, data: {request_id, device_id: b.execution.device_id, credential_version: b.execution.credential_version,
        batch_fingerprint: fingerprint, signing_payload: canonical({protocol: 'yike-candidate-submission-v1', tenant_id: 'tenant',
          user_id: session.userId, session_digest: 'a'.repeat(64), request_id, batch_fingerprint: fingerprint})}};
    }
    return {ok: true, status: 200, data: receipt};
  })};
  const options = {serviceOrigin: origin, journal, vault, transport};
  return {batch, receipt, session, options, events, key: {platformRunId: batch.execution.platform_run_id, requestId: batch.request_id},
    current: (value: boolean) => {current = value;}, create: () => createCandidateSession(options)};
}
it('persists original text before key/prepare/apply and returns validated acceptance', async () => {
  const f = fixture(); expect(await f.create().submit(f.session, f.batch)).toEqual({state: 'RECORDED', receipt: f.receipt});
  expect(f.events).toEqual(['persist', 'key', 'candidate.prepare', 'candidate.apply']);
  expect(f.options.journal.persist.mock.calls[0][1].records[0].body).toBe(f.batch.records[0].body);
});
it('reconstructed session and duplicate submit only GET the original composite key, without key/prepare', async () => {
  const f = fixture(); await f.create().submit(f.session, f.batch); f.events.length = 0;
  f.options.vault.read.mockRejectedValue(new Error('key gone'));
  expect(await f.create().recover(f.session, f.key)).toEqual({state: 'RECORDED', receipt: f.receipt});
  expect(f.events).toEqual(['read', 'candidate.receipt']); f.events.length = 0;
  expect(await f.create().submit(f.session, f.batch)).toMatchObject({state: 'RECORDED'});
  expect(f.events).toEqual(['persist', 'candidate.receipt']);
  expect(f.options.transport.requestCandidate.mock.lastCall![0]).toEqual({operation: 'candidate.receipt', payload: {
    platform_run_id: f.key.platformRunId, request_id: f.key.requestId}});
});
it('404 remains unknown, only explicit original retry prepares the saved unchanged batch', async () => {
  const f = fixture(); const client = f.create(); await client.submit(f.session, f.batch);
  const missing: ApiResult = {ok: false, status: 404, error: 'request_not_found'};
  f.options.transport.requestCandidate.mockResolvedValueOnce(missing); f.events.length = 0;
  expect(await client.recover(f.session, f.key)).toEqual({state: 'UNKNOWN', key: f.key});
  expect(f.events).toEqual(['read']); // The one-shot transport override deliberately emits no event.
  f.options.transport.requestCandidate.mockResolvedValueOnce(missing);
  expect(await client.recover(f.session, f.key, true)).toMatchObject({state: 'RECORDED'});
  expect(f.options.transport.requestCandidate.mock.lastCall![0].payload.batch).toEqual(f.batch);
});
it.each([0, 401, 403, 409, 500])('never retries HTTP %i even with explicit retry', async status => {
  const f = fixture(); await f.create().submit(f.session, f.batch); f.options.transport.requestCandidate.mockClear();
  f.options.transport.requestCandidate.mockResolvedValueOnce({ok: false, status, error: 'request_not_found'});
  expect(await f.create().recover(f.session, f.key, true)).toMatchObject({state: 'UNKNOWN'});
  expect(f.options.transport.requestCandidate).toHaveBeenCalledTimes(1);
});
it('does not treat an unrelated 404 as permission to retry', async () => {
  const f = fixture(); await f.create().submit(f.session, f.batch); f.options.transport.requestCandidate.mockClear();
  f.options.transport.requestCandidate.mockResolvedValueOnce({ok: false, status: 404, error: 'device_unavailable'});
  expect(await f.create().recover(f.session, f.key, true)).toMatchObject({state: 'UNKNOWN'});
  expect(f.options.transport.requestCandidate).toHaveBeenCalledTimes(1);
});
it('disk failure makes zero network requests and returns no private error', async () => {
  const f = fixture(); f.options.journal.persist.mockRejectedValue(new Error('private path/body'));
  expect(await f.create().submit(f.session, f.batch)).toEqual({state: 'FAILED', error: 'CANDIDATE_SESSION_FAILED'});
  expect(f.options.transport.requestCandidate).not.toHaveBeenCalled();
});
it('a bad success receipt is UNKNOWN, not acceptance or automatic retry', async () => {
  const f = fixture(); f.receipt.request_id = 'wrong';
  expect(await f.create().submit(f.session, f.batch)).toEqual({state: 'UNKNOWN', key: f.key});
  expect(f.events.filter(e => e === 'candidate.apply')).toHaveLength(1);
});
it.each(['persist', 'key', 'prepare', 'apply', 'read', 'list'])('guards session after %s wait', async stage => {
  const f = fixture();
  if (stage === 'read' || stage === 'list') await f.create().submit(f.session, f.batch);
  const target = stage === 'persist' ? f.options.journal.persist : stage === 'read' ? f.options.journal.read : stage === 'list' ? f.options.journal.list :
    stage === 'key' ? f.options.vault.read : f.options.transport.requestCandidate;
  const original = target.getMockImplementation()!;
  target.mockImplementation(async (...args: any[]) => {
    const value = await (original as any)(...args);
    if (stage !== 'prepare' && stage !== 'apply' || args[0].operation === 'candidate.' + stage) f.current(false);
    return value;
  });
  const client = f.create(); const result = stage === 'read' ? await client.recover(f.session, f.key) : stage === 'list' ? await client.list(f.session) : await client.submit(f.session, f.batch);
  expect(result).toEqual({state: 'SESSION_CHANGED'});
  if (stage !== 'apply' && stage !== 'read' && stage !== 'list') expect(f.events).not.toContain('candidate.apply');
});
it('guards final result after the inner list operation microtask', async () => {
  const f = fixture();
  f.options.journal.list.mockImplementation(async () => {
    queueMicrotask(() => queueMicrotask(() => f.current(false)));
    return [];
  });
  expect(await f.create().list(f.session)).toEqual({state: 'SESSION_CHANGED'});
});
it('snapshots input before the first asynchronous wait and blocks overlapping work', async () => {
  const f = fixture(); const client = f.create(); const original = f.options.journal.persist.getMockImplementation()!;
  let release!: () => void; const barrier = new Promise<void>(resolve => {release = resolve;});
  f.options.journal.persist.mockImplementation(async (...args) => {await barrier; return original(...args);});
  const pending = client.submit(f.session, f.batch); f.batch.records[0].body = 'changed';
  expect(await client.list(f.session)).toEqual({state: 'BUSY'}); release();
  expect(await pending).toMatchObject({state: 'RECORDED'});
  expect(f.options.transport.requestCandidate.mock.lastCall![0].payload.batch.records[0].body).not.toBe('changed');
});
it('rejects a journal returning a different original batch or key', async () => {
  const f = fixture(); const other = {...f.batch, request_id: 'wrong'};
  f.options.journal.persist.mockResolvedValue({batch: other, created: true});
  expect(await f.create().submit(f.session, f.batch)).toMatchObject({state: 'FAILED'});
  f.options.journal.read.mockResolvedValue(other);
  expect(await f.create().recover(f.session, f.key)).toMatchObject({state: 'FAILED'});
  expect(f.options.transport.requestCandidate).not.toHaveBeenCalled();
});
it('missing local batch makes no remote claim; historical listing returns only validated keys', async () => {
  const f = fixture(); expect(await f.create().recover(f.session, f.key)).toEqual({state: 'NOT_FOUND'});
  await f.create().submit(f.session, f.batch);
  expect(await f.create().list(f.session)).toEqual({state: 'LIST', keys: [f.key]});
});
it('wrong session or invalid keys fail before storage', async () => {
  const f = fixture(); const client = f.create();
  expect(await client.submit({...f.session, userId: ''}, f.batch)).toMatchObject({state: 'FAILED'});
  expect(await client.recover(f.session, {...f.key, platformRunId: '../escape'})).toMatchObject({state: 'FAILED'});
  expect(await client.recover(f.session, f.key, 'true')).toMatchObject({state: 'FAILED'});
  f.current(false); expect(await client.submit(f.session, f.batch)).toEqual({state: 'SESSION_CHANGED'});
  expect(f.events).toEqual([]);
});
