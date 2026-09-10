import {describe, expect, it} from 'vitest';
import {createDeviceIdentityController, type DeviceWorkerScope} from '../src/main/deviceIdentityController';
import type {DeviceIdentityResult} from '../src/main/deviceIdentitySession';
import type {ApiResult} from '../src/shared/contracts';

const ready = {state: 'READY', deviceId: '12345678-1234-4234-8234-123456789abc', credentialVersion: 1} as const;
const ok = (data: unknown = {}): ApiResult => ({ok: true, status: 200, data});
const auth = (user_id = 'TEST-owner') => ok({authenticated: true, user_id});
const changed = {ok: false, status: 0, error: 'SESSION_CHANGED'};
const unavailable = {ok: false, status: 0, error: 'SERVICE_UNAVAILABLE'};
const unauthorized = (): ApiResult => ({ok: false, status: 401, error: 'invalid_session'});
const families = ['requestExecution', 'requestCandidate', 'requestConnection', 'requestOutreach'] as const;
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((accept, fail) => {resolve = accept; reject = fail;});
  void promise.catch(() => {});
  return {promise, resolve, reject};
}
function fixture(candidateAvailable = true) {
  const state = {
    publicCalls: [] as unknown[], privateCalls: [] as {family: string; input: unknown}[],
    publicHandler: async (_input: unknown): Promise<ApiResult> => auth(),
    privateHandler: async (_input: unknown): Promise<ApiResult> => ok(),
    prepareResult: ready as DeviceIdentityResult,
  };
  const controller = createDeviceIdentityController({
    service: {
      async request(input) {state.publicCalls.push(input); return state.publicHandler(input);},
      async requestDevice() {throw new Error('unexpected device request');},
      async requestExecution(input) {state.privateCalls.push({family: 'requestExecution', input}); return state.privateHandler(input);},
      async requestConnection(input) {state.privateCalls.push({family: 'requestConnection', input}); return state.privateHandler(input);},
      async requestOutreach(input: unknown) {state.privateCalls.push({family: 'requestOutreach', input}); return state.privateHandler(input);},
      ...(candidateAvailable ? {async requestCandidate(input: unknown) {state.privateCalls.push({family: 'requestCandidate', input}); return state.privateHandler(input);}} : {}),
    },
    identityFactory: () => ({async prepare() {return state.prepareResult;}}),
  });
  return {state, controller};
}
type ReadyScope = DeviceWorkerScope & {transport:{requestOutreach(input:unknown):Promise<ApiResult>}};
async function open(f: ReturnType<typeof fixture>): Promise<ReadyScope> {
  expect(await f.controller.prepare()).toEqual(ready);
  const result = await f.controller.openWorkerScope();
  expect(result.ok).toBe(true);
  if (!result.ok) throw new Error('scope must open');
  expect(typeof result.scope.transport.requestOutreach).toBe('function');
  return result.scope as ReadyScope;
}

describe('bounded main-only device worker scope', () => {
  it('reads fresh authenticated main identity and copies READY without preparing again', async () => {
    const f = fixture(); const scope = await open(f);
    expect(f.state.publicCalls).toEqual([{operation: 'session.get'}, {operation: 'session.get'}]);
    expect(scope.session.userId).toBe('TEST-owner');
    expect(scope.session.isCurrent()).toBe(true);
    expect(scope.device).toEqual({deviceId: ready.deviceId, credentialVersion: 1});
    scope.device.credentialVersion = 9;
    expect(f.controller.getStatus()).toEqual(ready);
    expect(await scope.transport.requestExecution({operation: 'execution.start'})).toEqual(ok());
    expect(await scope.transport.requestCandidate({operation: 'candidate.submit'})).toEqual(ok());
    expect(await scope.transport.requestConnection({operation: 'connections.current'})).toEqual(ok());
    expect(await scope.transport.requestOutreach?.({operation:'outreach.dispatch.receipt',payload:{requestId:ready.deviceId}})).toEqual(ok());
    expect(await f.controller.requestExecution({operation: 'execution.start'})).toEqual(changed);
    expect(f.state.privateCalls.map(call => call.family)).toEqual([...families]);
  });

  it.each(['NOT_PREPARED', 'KEY_MISSING', 'REVOKED', 'FAILED'] as const)('requires READY, not %s', async state => {
    const f = fixture();
    if (state !== 'NOT_PREPARED') {f.state.prepareResult = {state}; await f.controller.prepare();}
    expect(await f.controller.openWorkerScope()).toEqual({ok: false, state: 'DEVICE_NOT_READY'});
    expect(f.state.privateCalls).toEqual([]);
  });

  it.each([ok({authenticated: false}), unauthorized()])('signed out observations reject scope and invalidate old scope %#', async response => {
    const f = fixture(); const old = await open(f); f.state.publicHandler = async () => response;
    expect(await f.controller.openWorkerScope()).toEqual({ok: false, state: 'SIGNED_OUT'});
    expect(old.session.isCurrent()).toBe(false);
    expect(f.controller.getStatus()).toEqual({state: 'SIGNED_OUT'});
  });

  it.each([
    {authenticated: true, user_id: 'TEST-new', extra: 'untrusted'},
    {authenticated: true, user_id: '\ud800'},
    {authenticated: false, user_id: 'TEST-new'},
  ])('malformed new-user observations invalidate prior READY and scope %#', async data => {
    const f = fixture(); const old = await open(f); f.state.publicHandler = async () => ok(data);
    expect(await f.controller.openWorkerScope()).toEqual({ok: false, state: 'FAILED'});
    expect(old.session.isCurrent()).toBe(false);
    expect(f.controller.getStatus()).toEqual({state: 'FAILED', error: 'DEVICE_IDENTITY_FAILED'});
  });

  it('a valid newly observed user cannot inherit old READY', async () => {
    const f = fixture(); const old = await open(f); f.state.publicHandler = async () => auth('TEST-new');
    expect(await f.controller.openWorkerScope()).toEqual({ok: false, state: 'DEVICE_NOT_READY'});
    expect(old.session.isCurrent()).toBe(false);
    expect(f.controller.getStatus()).toEqual({state: 'NOT_PREPARED'});
    const current = await open(f);
    expect(current.session.userId).toBe('TEST-new');
    expect(current.session.sessionId).not.toBe(old.session.sessionId);
  });

  it.each(['error', 'reject'] as const)('sanitizes authentication %s and releases the short lock', async outcome => {
    const f = fixture(); await f.controller.prepare();
    f.state.publicHandler = async () => {if (outcome === 'reject') throw new Error('/private/token'); return unavailable as ApiResult;};
    expect(await f.controller.openWorkerScope()).toEqual({ok: false, state: 'FAILED'});
    f.state.publicHandler = async () => auth();
    expect((await f.controller.openWorkerScope()).ok).toBe(true);
  });

  it('holds the busy guard only for opening, not while a browser worker or cancellation runs', async () => {
    const f = fixture(); const scope = await open(f);
    const blocked = deferred<ApiResult>(); f.state.privateHandler = async () => blocked.promise;
    const work = scope.transport.requestCandidate({operation: 'candidate.submit'});
    f.state.privateHandler = async () => ok('cancelled');
    expect(await f.controller.withAuthenticatedSession(session => {
      expect(session.sessionId).toBe(scope.session.sessionId);
      return f.controller.requestExecution({operation: 'execution.cancel'});
    })).toEqual({ok: true, value: ok('cancelled')});
    blocked.resolve(ok('submitted')); expect(await work).toEqual(ok('submitted'));
    expect(await scope.transport.requestExecution({operation: 'execution.poll'})).toEqual(ok('cancelled'));
  });

  it('rejects competing opens while fresh authentication is pending', async () => {
    const f = fixture(); await f.controller.prepare(); const pending = deferred<ApiResult>();
    f.state.publicHandler = async () => pending.promise;
    const opening = f.controller.openWorkerScope();
    expect(await f.controller.openWorkerScope()).toEqual({ok: false, state: 'BUSY'});
    expect(await f.controller.withAuthenticatedSession(async () => 'no')).toEqual({ok: false, state: 'BUSY'});
    pending.resolve(auth()); expect((await opening).ok).toBe(true);
  });

  it.each(['session.login', 'session.loginPhone', 'session.logout'])('invalidates on %s entry, including pending same-user login', async operation => {
    const f = fixture(); const old = await open(f); const pending = deferred<ApiResult>();
    f.state.publicHandler = async () => pending.promise;
    const change = f.controller.requestApi({operation});
    expect(old.session.isCurrent()).toBe(false);
    for (const family of families) expect(await old.transport[family]({})).toEqual(changed);
    expect(f.state.privateCalls).toEqual([]);
    expect(await f.controller.openWorkerScope()).toEqual({ok: false, state: 'BUSY'});
    pending.resolve(auth()); await change; f.state.publicHandler = async () => auth();
    const current = await open(f);
    expect(current.session.sessionId).not.toBe(old.session.sessionId);
  });

  it.each(['success', '401', 'reject'] as const)('discards a late opening session %s after logout', async outcome => {
    const f = fixture(); await f.controller.prepare(); const pending = deferred<ApiResult>();
    f.state.publicHandler = async input => (input as {operation: string}).operation === 'session.get' ? pending.promise : ok();
    const opening = f.controller.openWorkerScope(); await f.controller.requestApi({operation: 'session.logout'});
    if (outcome === 'reject') pending.reject(new Error('/private/auth')); else pending.resolve(outcome === '401' ? unauthorized() : auth());
    expect(await opening).toEqual({ok: false, state: 'SESSION_CHANGED'});
    expect(f.controller.getStatus()).toEqual({state: 'SIGNED_OUT'});
  });

  it('close is idempotent and blocks both families without changing another scope', async () => {
    const f = fixture(); const old = await open(f); const other = await f.controller.openWorkerScope();
    expect(other.ok).toBe(true); old.close(); old.close();
    expect(old.session.isCurrent()).toBe(false);
    for (const family of families) expect(await old.transport[family]({})).toEqual(changed);
    expect(f.state.privateCalls).toEqual([]);
    if (other.ok) expect(other.scope.session.isCurrent()).toBe(true);
    expect(f.controller.getStatus()).toEqual(ready);
  });

  it.each(families)('%s 401 invalidates its initiating epoch and all same-session scopes', async family => {
    const f = fixture(); const scope = await open(f); const other = await f.controller.openWorkerScope();
    f.state.privateHandler = async () => unauthorized();
    expect(await scope.transport[family]({})).toEqual(unauthorized());
    expect(scope.session.isCurrent()).toBe(false);
    if (other.ok) expect(other.scope.session.isCurrent()).toBe(false);
    expect(f.controller.getStatus()).toEqual({state: 'SIGNED_OUT'});
  });

  it.each(families)('%s sanitizes private exceptions', async family => {
    const f = fixture(); const scope = await open(f);
    f.state.privateHandler = async () => {throw new Error('/private/credential');};
    expect(await scope.transport[family]({})).toEqual(unavailable);
    expect(scope.session.isCurrent()).toBe(true);
  });

  it.each(families.flatMap(family => ['success', '401', 'reject'].flatMap(outcome => ['close', 'login'].map(change => ({family, outcome, change})))))('drops late $family $outcome after $change without leaking or mutating new state', async ({family, outcome, change}) => {
    const f = fixture(); const old = await open(f); const pending = deferred<ApiResult>();
    f.state.privateHandler = async () => pending.promise;
    const response = old.transport[family]({});
    if (change === 'close') old.close(); else await f.controller.requestApi({operation: 'session.login'});
    const current = await open(f);
    if (outcome === 'reject') pending.reject(new Error('/private/late')); else pending.resolve(outcome === '401' ? unauthorized() : ok({secret: 'late'}));
    expect(await response).toEqual(changed);
    expect(current.session.isCurrent()).toBe(true);
    expect(f.controller.getStatus()).toEqual(ready);
    expect(await old.transport[family]({})).toEqual(changed);
    expect(f.state.privateCalls).toHaveLength(1);
  });

  it('missing candidate service fails closed without renderer/public fallback', async () => {
    const f = fixture(false); const scope = await open(f);
    expect(await scope.transport.requestCandidate({operation: 'candidate.submit'})).toEqual(unavailable);
    expect(f.state.publicCalls).toHaveLength(2);
    expect(f.state.privateCalls).toEqual([]);
    expect(await f.controller.requestApi({operation: 'candidate.submit'})).toEqual(auth());
    expect(f.state.privateCalls).toEqual([]);
  });
});
