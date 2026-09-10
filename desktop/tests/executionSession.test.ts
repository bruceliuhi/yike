import {createHash, generateKeyPairSync} from 'node:crypto';
import {describe, expect, it, vi} from 'vitest';
import {createExecutionSession} from '../src/main/executionSession';
import {executionOperationSchema, type ExecutionOperation} from '../src/shared/executionOperation';
import type {ApiResult} from '../src/shared/contracts';

const id = '00000000-0000-0000-0000-000000000001';
const task = '00000000-0000-0000-0000-000000000002';
const origin = 'https://test.example';
function canonical(v: any): string {
  if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']';
  if (v && typeof v === 'object') return '{' + Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + canonical(v[k])).join(',') + '}';
  return JSON.stringify(v);
}
function fixture() {
  const request = executionOperationSchema.parse({schema_version: 'execution-runtime-v1', request_id: id,
    device_id: id, credential_version: 1, operation: 'CANCEL', task_id: task});
  const receipt = {schema_version: request.schema_version, request_id: id, operation: 'CANCEL',
    task_id: task, run_id: id, status: 'CANCELED', stop_confirmed: true};
  let saved: ExecutionOperation | null = null;
  let current = true;
  const events: string[] = [];
  const session = {userId: 'test-user', sessionId: id, isCurrent: () => current};
  const pair = generateKeyPairSync('ed25519');
  const key = {scope: {serviceOrigin: origin, userId: session.userId, deviceId: id},
    privateKey: pair.privateKey.export({format: 'pem', type: 'pkcs8'}).toString(), publicKey: pair.publicKey.export({format: 'jwk'}).x!};
  const journal = {
    persist: vi.fn(async (_scope, value: ExecutionOperation) => {
      events.push('persist'); const created = saved === null;
      if (saved && canonical(saved) !== canonical(value)) throw new Error('conflict');
      saved = structuredClone(value); return {request: structuredClone(saved), created};
    }),
    read: vi.fn(async () => {events.push('read'); return saved && structuredClone(saved);}),
    list: vi.fn(async () => saved ? [structuredClone(saved)] : []),
  };
  const vault = {read: vi.fn(async () => {events.push('key'); return key;})};
  const transport = {requestExecution: vi.fn(async (input: any): Promise<ApiResult> => {
    events.push(input.operation);
    if (input.operation === 'execution.prepare') {
      const r = input.payload.request;
      return {ok: true, status: 200, data: {request_id: r.request_id, device_id: r.device_id,
        credential_version: r.credential_version,
        request_sha256: createHash('sha256').update(canonical(r)).digest('hex'),
        signing_payload: canonical({protocol: 'yike-execution-operation-v1', tenant_id: 'tenant',
          user_id: session.userId, session_digest: 'a'.repeat(64), operation: r})}};
    }
    return {ok: true, status: 200, data: receipt};
  })};
  const options = {serviceOrigin: origin, journal, vault, transport};
  return {request, receipt, session, options, events, setCurrent: (value: boolean) => {current = value;},
    saved: () => saved, create: () => createExecutionSession(options)};
}

describe('durable original execution session', () => {
  it('persists before signing/apply and keeps a validated receipt distinct from current authorization', async () => {
    const f = fixture();
    expect(await f.create().submit(f.session, f.request)).toEqual({state: 'RECORDED', receipt: f.receipt});
    expect(f.events[0]).toBe('persist');
    expect(f.events).toContain('execution.prepare');
    expect(f.events.at(-1)).toBe('execution.apply');
    expect(f.saved()).toEqual(f.request);
    expect(JSON.stringify(f.saved())).not.toContain('signature');
  });
  it('reconstructs then queries only the original UUID without needing a device key', async () => {
    const f = fixture(); await f.create().submit(f.session, f.request);
    f.events.length = 0;
    f.options.vault.read.mockRejectedValue(new Error('missing key'));
    expect(await f.create().recover(f.session, id)).toEqual({state: 'RECORDED', receipt: f.receipt});
    expect(f.events).toEqual(['read', 'execution.receipt']);
  });
  it('a second submit of an existing request is recovery, not another POST', async () => {
    const f = fixture(); const client = f.create(); await client.submit(f.session, f.request);
    f.events.length = 0;
    expect(await client.submit(f.session, f.request)).toMatchObject({state: 'RECORDED'});
    expect(f.events).toEqual(['persist', 'execution.receipt']);
  });
  it('404 preserves unknown; only explicit original retry obtains fresh signing bytes', async () => {
    const f = fixture(); const client = f.create(); await client.submit(f.session, f.request);
    const missing: ApiResult = {ok: false, status: 404, error: 'request_not_found'};
    f.options.transport.requestExecution.mockResolvedValueOnce(missing);
    f.events.length = 0;
    expect(await client.recover(f.session, id)).toEqual({state: 'UNKNOWN', requestId: id});
    expect(f.events).not.toContain('execution.apply');
    f.options.transport.requestExecution.mockResolvedValueOnce(missing);
    expect(await client.recover(f.session, id, true, {deviceId: id, credentialVersion: 1})).toEqual({state: 'RECORDED', receipt: f.receipt});
    expect(f.events).toContain('execution.prepare');
  });
  it.each([
    {deviceId: task, credentialVersion: 1},
    {deviceId: id, credentialVersion: 2},
  ])('rejects mutating retry when current READY binding differs from the original journal request %#', async device => {
    const f = fixture(); const client = f.create(); await client.submit(f.session, f.request);
    f.events.length = 0;
    expect(await client.recover(f.session, id, true, device)).toEqual({state: 'DEVICE_NOT_READY'});
    expect(f.events).toEqual(['read']);
  });
  it('fences a retry when the authenticated identity changes while receipt lookup is pending', async () => {
    const f = fixture(); const client = f.create(); await client.submit(f.session, f.request);
    f.events.length = 0;
    f.options.transport.requestExecution.mockImplementationOnce(async () => {
      f.setCurrent(false);
      return {ok: false, status: 404, error: 'request_not_found'};
    });
    expect(await client.recover(f.session, id, true, {deviceId: id, credentialVersion: 1})).toEqual({state: 'SESSION_CHANGED'});
    expect(f.events).toEqual(['read']);
    expect(f.options.transport.requestExecution.mock.calls.at(-1)?.[0]).toMatchObject({operation: 'execution.receipt'});
    expect(f.options.transport.requestExecution.mock.calls.slice(-1).some(([input]) =>
      input.operation === 'execution.prepare' || input.operation === 'execution.apply')).toBe(false);
  });
  it.each([401, 403, 409, 500])('does not retry recovery HTTP %i', async status => {
    const f = fixture(); const client = f.create(); await client.submit(f.session, f.request);
    f.options.transport.requestExecution.mockResolvedValueOnce({ok: false, status, error: 'request_not_found'});
    f.events.length = 0;
    expect(await client.recover(f.session, id, true, {deviceId: id, credentialVersion: 1})).toMatchObject({state: 'UNKNOWN'});
    expect(f.events).toEqual(['read']);
  });
  it('never fetches after disk failure', async () => {
    const f = fixture(); f.options.journal.persist.mockRejectedValue(new Error('private path'));
    expect(await f.create().submit(f.session, f.request)).toEqual({state: 'FAILED', error: 'EXECUTION_SESSION_FAILED'});
    expect(f.options.transport.requestExecution).not.toHaveBeenCalled();
  });
  it('returns unknown for lost/malformed apply without retry', async () => {
    const f = fixture(); const real = f.options.transport.requestExecution.getMockImplementation()!;
    f.options.transport.requestExecution.mockImplementation(async input => input.operation === 'execution.apply'
      ? {ok: true, status: 200, data: {...f.receipt, request_id: task}} : real(input));
    expect(await f.create().submit(f.session, f.request)).toEqual({state: 'UNKNOWN', requestId: id});
    expect(f.events.filter(e => e === 'execution.prepare')).toHaveLength(1);
    expect(f.saved()).toEqual(f.request);
  });
  it('session invalidation after preparation prevents apply', async () => {
    const f = fixture(); const real = f.options.transport.requestExecution.getMockImplementation()!;
    f.options.transport.requestExecution.mockImplementation(async input => {
      const result = await real(input); f.setCurrent(false); return result;
    });
    expect(await f.create().submit(f.session, f.request)).toEqual({state: 'SESSION_CHANGED'});
    expect(f.events).not.toContain('execution.apply');
  });
  it('lists saved original operations without HTTP and rejects invalid session', async () => {
    const f = fixture(); const client = f.create(); await client.submit(f.session, f.request);
    f.options.transport.requestExecution.mockClear();
    expect(await client.list(f.session)).toEqual({state: 'LIST', requests: [f.request]});
    expect(f.options.transport.requestExecution).not.toHaveBeenCalled();
    f.setCurrent(false);
    expect(await client.list(f.session)).toEqual({state: 'SESSION_CHANGED'});
  });
  it('does not recreate missing original intent on recovery', async () => {
    const f = fixture(); expect(await f.create().recover(f.session, id, true, {deviceId: id, credentialVersion: 1})).toEqual({state: 'NOT_FOUND'});
    expect(f.options.journal.persist).not.toHaveBeenCalled();
    expect(f.options.transport.requestExecution).not.toHaveBeenCalled();
  });
  it('snapshots caller input before disk await and rejects concurrent work as busy', async () => {
    const f = fixture(); const client = f.create();
    let release!: () => void;
    const gate = new Promise<void>(resolve => {release = resolve;});
    const real = f.options.journal.persist.getMockImplementation()!;
    f.options.journal.persist.mockImplementation(async (scope, request) => {await gate; return real(scope, request);});
    const input = structuredClone(f.request);
    const pending = client.submit(f.session, input);
    input.task_id = id;
    expect(await client.submit(f.session, input)).toEqual({state: 'BUSY'});
    release();
    expect(await pending).toEqual({state: 'RECORDED', receipt: f.receipt});
    expect(f.saved()).toEqual(f.request);
  });
  it('retains the original intent if epoch changes during disk write', async () => {
    const f = fixture(); const real = f.options.journal.persist.getMockImplementation()!;
    f.options.journal.persist.mockImplementation(async (scope, request) => {
      const result = await real(scope, request); f.setCurrent(false); return result;
    });
    expect(await f.create().submit(f.session, f.request)).toEqual({state: 'SESSION_CHANGED'});
    expect(f.saved()).toEqual(f.request);
    expect(f.options.transport.requestExecution).not.toHaveBeenCalled();
  });
  it('lost apply remains UNKNOWN and keeps the original intent without automatic retry', async () => {
    const f = fixture(); const real = f.options.transport.requestExecution.getMockImplementation()!;
    f.options.transport.requestExecution.mockImplementation(async input => {
      if (input.operation === 'execution.apply') throw new Error('private network details');
      return real(input);
    });
    expect(await f.create().submit(f.session, f.request)).toEqual({state: 'UNKNOWN', requestId: id});
    expect(f.options.transport.requestExecution).toHaveBeenCalledTimes(2);
    expect(f.saved()).toEqual(f.request);
  });
  it('rejects an epoch change between the final storage guard and returning the list', async () => {
    const f = fixture();
    f.options.journal.list.mockImplementation(async () => {
      queueMicrotask(() => queueMicrotask(() => f.setCurrent(false)));
      return [f.request];
    });
    expect(await f.create().list(f.session)).toEqual({state: 'SESSION_CHANGED'});
  });
});
