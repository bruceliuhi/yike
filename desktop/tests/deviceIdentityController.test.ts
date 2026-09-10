import {describe, expect, it} from 'vitest';
import {createDeviceIdentityController} from '../src/main/deviceIdentityController';
import {deviceIdentityRetrySchema, deviceIdentityStatusSchema, GET_DEVICE_IDENTITY_STATUS_CHANNEL, PREPARE_DEVICE_IDENTITY_CHANNEL, type DeviceIdentityRetry} from '../src/shared/deviceIdentity';
import type {DeviceIdentityResult, DeviceIdentitySessionInput} from '../src/main/deviceIdentitySession';
import type {ApiResult} from '../src/shared/contracts';

const deviceId = '12345678-1234-4234-8234-123456789abc';
const ready = {state: 'READY', deviceId, credentialVersion: 1} as const;
const failed = {state: 'FAILED', error: 'DEVICE_IDENTITY_FAILED'} as const;
const signedOut = {state: 'SIGNED_OUT'} as const;
const ok = (data: unknown): ApiResult => ({ok: true, status: 200, data});
const unauthorized = (): ApiResult => ({ok: false, status: 401, error: 'invalid_session'});
const auth = (user_id = 'TEST-owner') => ok({authenticated: true, user_id});
const logout = {operation: 'session.logout'};
const login = {operation: 'session.login', payload: {token: 'TEST-short-lived-token'}};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((accept, fail) => {resolve = accept; reject = fail;});
  void promise.catch(() => {}); // A RED stub may not yet consume this test-owned deferred.
  return {promise, resolve, reject};
}

function fixture() {
  const state = {
    publicCalls: [] as unknown[], privateCalls: [] as unknown[],
    prepares: [] as {session: DeviceIdentitySessionInput; retry: DeviceIdentityRetry}[],
    publicHandler: async (_input: unknown): Promise<ApiResult> => auth(),
    privateHandler: async (_input: unknown): Promise<ApiResult> => ok({}),
    prepareHandler: async (_session: DeviceIdentitySessionInput, _retry: DeviceIdentityRetry, _transport: {requestDevice(input: unknown): Promise<ApiResult>}): Promise<DeviceIdentityResult> => ready,
  };
  const controller = createDeviceIdentityController({
    service: {
      async request(input) {state.publicCalls.push(structuredClone(input)); return state.publicHandler(input);},
      async requestDevice(input) {state.privateCalls.push(structuredClone(input)); return state.privateHandler(input);},
    },
    identityFactory: transport => ({async prepare(session, retry) {
      state.prepares.push({session, retry: structuredClone(retry)});
      return state.prepareHandler(session, retry, transport);
    }}),
  });
  return {state, controller};
}

describe('narrow shared device identity contract', () => {
  it('has fixed channels, default-empty retry options, and exact booleans only', () => {
    expect(GET_DEVICE_IDENTITY_STATUS_CHANNEL).toBe('desktop:get-device-identity-status');
    expect(PREPARE_DEVICE_IDENTITY_CHANNEL).toBe('desktop:prepare-device-identity');
    expect(deviceIdentityRetrySchema.safeParse(undefined)).toMatchObject({success: true, data: {}});
    expect(deviceIdentityRetrySchema.safeParse({retryProof: false, retryRegistration: true})).toMatchObject({success: true, data: {retryProof: false, retryRegistration: true}});
    for (const value of [null, [], true, {retryProof: 1}, {retryRegistration: 'true'}, {userId: 'forged'}, {sessionId: 'forged'}, {operation: 'devices.complete'}, {headers: {}}, {url: 'https://other.example'}]) {
      expect(deviceIdentityRetrySchema.safeParse(value).success).toBe(false);
    }
  });
  it.each([
    ready, {state: 'NOT_PREPARED'}, signedOut, {state: 'BUSY'}, {state: 'SERVICE_UNAVAILABLE'}, {state: 'INVALID_REQUEST'},
    ...['REGISTRATION_UNKNOWN', 'PROOF_UNKNOWN', 'REVOKED', 'KEY_MISSING', 'KEY_MISMATCH', 'SESSION_CHANGED', 'FAILED'].map(state => ({state})),
    failed, {state: 'FAILED', error: 'DEVICE_IDENTITY_VERSION_CHANGED'},
  ])('accepts safe status $state', value => expect(deviceIdentityStatusSchema.safeParse(value)).toMatchObject({success: true, data: value}));
  it.each([
    null, [], {}, {state: 'anything'}, {...ready, deviceId: deviceId.toUpperCase()}, {...ready, deviceId: '../private'},
    {...ready, credentialVersion: 0}, {...ready, credentialVersion: '1'}, {...ready, credentialVersion: 1.2},
    {...ready, privateKey: 'secret'}, {...ready, error: 'DEVICE_IDENTITY_FAILED'},
    {state: 'FAILED', error: '/private/path'}, {state: 'FAILED', cause: 'secret'}, {state: 'SIGNED_OUT', userId: 'owner'},
  ])('rejects unsafe or malformed status %#', value => expect(deviceIdentityStatusSchema.safeParse(value).success).toBe(false));
  it('bounds READY credentialVersion to the server integer range', () => {
    expect(deviceIdentityStatusSchema.safeParse({...ready, credentialVersion: 2_147_483_647}).success).toBe(true);
    expect(deviceIdentityStatusSchema.safeParse({...ready, credentialVersion: 2_147_483_648}).success).toBe(false);
  });
});

describe('main device identity controller', () => {
  it('starts NOT_PREPARED, reads a real authenticated user and returns only a copied safe status', async () => {
    const f = fixture();
    expect(f.controller.getStatus()).toEqual({state: 'NOT_PREPARED'});
    expect(f.state.publicCalls).toEqual([]);
    const result = await f.controller.prepare();
    expect(result).toEqual(ready);
    expect(f.state.publicCalls).toEqual([{operation: 'session.get'}]);
    expect(f.state.prepares).toHaveLength(1);
    expect(f.state.prepares[0].session.userId).toBe('TEST-owner');
    expect(f.state.prepares[0].session.sessionId).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
    expect(f.state.prepares[0].session.isCurrent()).toBe(true);
    Object.assign(result, {state: 'FAILED'});
    const observed = f.controller.getStatus(); Object.assign(observed, {state: 'SIGNED_OUT'});
    expect(f.controller.getStatus()).toEqual(ready);
    expect(f.state.publicCalls).toHaveLength(1); // Status is an observation, not a fresh authorization read.
  });

  it('preserves an epoch on repeated same-user observations and changes it on an observed user switch', async () => {
    const f = fixture();
    expect(await f.controller.prepare()).toEqual(ready);
    expect(await f.controller.prepare()).toEqual(ready);
    expect(f.state.prepares[1].session.sessionId).toBe(f.state.prepares[0].session.sessionId);
    f.state.publicHandler = async () => auth('TEST-next-owner');
    expect(await f.controller.prepare()).toEqual(ready);
    expect(f.state.prepares[2].session.userId).toBe('TEST-next-owner');
    expect(f.state.prepares[2].session.sessionId).not.toBe(f.state.prepares[0].session.sessionId);
    expect(f.state.prepares[0].session.isCurrent()).toBe(false);
  });

  it.each([login, {operation: 'session.loginPhone', payload: {phone: '13800138000', code: '123456'}}, logout])('invalidates immediately on $operation, even when the next login is the same user', async request => {
    const f = fixture(); expect(await f.controller.prepare()).toEqual(ready);
    const old = f.state.prepares[0].session;
    const pendingAuth = deferred<ApiResult>(); f.state.publicHandler = async () => pendingAuth.promise;
    const pending = f.controller.requestApi(request);
    expect(old.isCurrent()).toBe(false);
    expect(f.controller.getStatus()).toEqual({state: request.operation === 'session.logout' ? 'SIGNED_OUT' : 'NOT_PREPARED'});
    expect(await f.controller.prepare()).toEqual({state: 'BUSY'});
    pendingAuth.resolve(auth()); await pending;
    f.state.publicHandler = async () => auth();
    expect(await f.controller.prepare()).toEqual(ready);
    expect(f.state.prepares[1].session.sessionId).not.toBe(old.sessionId);
  });

  it('keeps all concurrent authentication calls pending until the last one settles', async () => {
    const f = fixture(); const first = deferred<ApiResult>(); const second = deferred<ApiResult>();
    let calls = 0; f.state.publicHandler = async () => (++calls === 1 ? first.promise : second.promise);
    const a = f.controller.requestApi(login); const b = f.controller.requestApi(logout);
    first.resolve(auth()); await a;
    expect(await f.controller.prepare()).toEqual({state: 'BUSY'});
    expect(f.state.publicCalls).toHaveLength(2);
    expect(f.controller.getStatus()).toEqual(signedOut);
    second.resolve(ok({authenticated: false})); await b;
    f.state.publicHandler = async () => auth();
    expect(await f.controller.prepare()).toEqual(ready);
  });

  it('an older public 401 cannot invalidate a newly authenticated epoch or overwrite its READY', async () => {
    const f = fixture(); expect(await f.controller.prepare()).toEqual(ready);
    const old = deferred<ApiResult>(); f.state.publicHandler = async input => (input as {operation: string}).operation === 'profiles.list' ? old.promise : auth();
    const request = f.controller.requestApi({operation: 'profiles.list'});
    await f.controller.requestApi(login);
    expect(await f.controller.prepare()).toEqual(ready);
    const current = f.state.prepares.at(-1)!.session;
    old.resolve(unauthorized()); expect(await request).toEqual(unauthorized());
    expect(current.isCurrent()).toBe(true);
    expect(f.controller.getStatus()).toEqual(ready);
  });

  it('a current public 401 immediately clears remembered READY and invalidates its epoch', async () => {
    const f = fixture(); expect(await f.controller.prepare()).toEqual(ready);
    f.state.publicHandler = async () => unauthorized();
    expect(await f.controller.requestApi({operation: 'profiles.list'})).toEqual(unauthorized());
    expect(f.controller.getStatus()).toEqual(signedOut);
    expect(f.state.prepares[0].session.isCurrent()).toBe(false);
  });

  it('delegates original public requests without exposing private device operations', async () => {
    const f = fixture(); const request = {operation: 'devices.complete', payload: {private: 'forged'}};
    f.state.publicHandler = async () => ({ok: false, status: 0, error: 'INVALID_API_REQUEST'});
    expect(await f.controller.requestApi(request)).toEqual({ok: false, status: 0, error: 'INVALID_API_REQUEST'});
    expect(f.state.publicCalls).toEqual([request]);
    expect(f.state.privateCalls).toEqual([]);
  });

  it.each([null, [], 'retry', {userId: 'forged'}, {sessionId: 'forged'}, {retryProof: 'true'}, {retryRegistration: 1}, {signing_payload: 'secret'}, {url: 'https://other.example'}])('rejects malicious prepare input %# without service calls', async input => {
    const f = fixture();
    expect(await f.controller.prepare(input)).toEqual({state: 'INVALID_REQUEST'});
    expect(f.state.publicCalls).toEqual([]); expect(f.state.privateCalls).toEqual([]); expect(f.state.prepares).toEqual([]);
  });

  it('snapshots retry flags before the session read awaits', async () => {
    const f = fixture(); const response = deferred<ApiResult>(); f.state.publicHandler = async () => response.promise;
    const retry = {retryRegistration: false, retryProof: true};
    const pending = f.controller.prepare(retry);
    retry.retryRegistration = true; retry.retryProof = false;
    response.resolve(auth());
    expect(await pending).toEqual(ready);
    expect(f.state.prepares[0].retry).toEqual({retryRegistration: false, retryProof: true});
  });

  it('blocks duplicate prepare without extra network/identity work and does not overwrite current observation', async () => {
    const f = fixture(); const response = deferred<ApiResult>(); f.state.publicHandler = async () => response.promise;
    const pending = f.controller.prepare();
    const status = f.controller.getStatus();
    expect(await f.controller.prepare()).toEqual({state: 'BUSY'});
    expect(f.controller.getStatus()).toEqual(status);
    expect(f.state.publicCalls).toEqual([{operation: 'session.get'}]);
    response.resolve(auth()); expect(await pending).toEqual(ready);
    f.state.publicHandler = async () => auth();
    expect(await f.controller.prepare()).toEqual(ready);
  });

  it.each(['resolve', 'reject'] as const)('logout during session read suppresses a late %s without entering the coordinator', async outcome => {
    const f = fixture(); const response = deferred<ApiResult>();
    f.state.publicHandler = async input => (input as {operation: string}).operation === 'session.get' ? response.promise : ok({authenticated: false});
    const pending = f.controller.prepare();
    await f.controller.requestApi(logout);
    if (outcome === 'resolve') response.resolve(auth()); else response.reject(new Error('/private/token'));
    expect(await pending).toEqual({state: 'SESSION_CHANGED'});
    expect(f.state.prepares).toEqual([]);
    expect(f.controller.getStatus()).toEqual(signedOut);
  });

  it.each(['resolve', 'reject'] as const)('logout during coordinator work suppresses a late %s without restoring READY', async outcome => {
    const f = fixture(); const result = deferred<DeviceIdentityResult>(); const started = deferred<void>();
    f.state.prepareHandler = async () => {started.resolve(); return result.promise;};
    const pending = f.controller.prepare(); await Promise.race([started.promise, pending]);
    expect(f.state.prepares).toHaveLength(1);
    const previous = f.state.prepares[0].session;
    await f.controller.requestApi(logout);
    expect(previous.isCurrent()).toBe(false);
    if (outcome === 'resolve') result.resolve(ready); else result.reject(new Error('/private/key'));
    expect(await pending).toEqual({state: 'SESSION_CHANGED'});
    expect(f.controller.getStatus()).toEqual(signedOut);
  });

  it('current private 401 invalidates the preparing epoch and clears state even if coordinator returns READY', async () => {
    const f = fixture(); f.state.privateHandler = async () => unauthorized();
    f.state.prepareHandler = async (_session, _retry, transport) => {await transport.requestDevice({operation: 'devices.identity', payload: {device_id: deviceId}}); return ready;};
    expect(await f.controller.prepare()).toEqual({state: 'SESSION_CHANGED'});
    expect(f.controller.getStatus()).toEqual(signedOut);
    expect(f.state.prepares[0].session.isCurrent()).toBe(false);
  });

  it('old private 401 after login cannot invalidate the new epoch', async () => {
    const f = fixture(); const response = deferred<ApiResult>(); const started = deferred<void>();
    f.state.privateHandler = async () => {started.resolve(); return response.promise;};
    f.state.prepareHandler = async (_session, _retry, transport) => {await transport.requestDevice({operation: 'devices.identity', payload: {device_id: deviceId}}); return ready;};
    const pending = f.controller.prepare(); await Promise.race([started.promise, pending]);
    expect(f.state.privateCalls).toHaveLength(1);
    await f.controller.requestApi(login);
    response.resolve(unauthorized());
    expect(await pending).toEqual({state: 'SESSION_CHANGED'});
    expect(f.controller.getStatus()).toEqual({state: 'NOT_PREPARED'});
    f.state.prepareHandler = async () => ready;
    expect(await f.controller.prepare()).toEqual(ready);
    expect(f.state.prepares.at(-1)!.session.isCurrent()).toBe(true);
  });

  it.each(['resolve', 'reject'] as const)('the private boundary suppresses a stale %s before returning to the old coordinator', async outcome => {
    const f = fixture(); const response = deferred<ApiResult>(); const started = deferred<void>();
    let delivered: unknown;
    f.state.privateHandler = async () => {started.resolve(); return response.promise;};
    f.state.prepareHandler = async (_session, _retry, transport) => {
      try { delivered = await transport.requestDevice({operation: 'devices.identity', payload: {device_id: deviceId}}); }
      catch (error) { delivered = error; }
      return ready;
    };
    const pending = f.controller.prepare(); await Promise.race([pending, started.promise]);
    expect(f.state.privateCalls).toHaveLength(1);
    await f.controller.requestApi(logout);
    if (outcome === 'resolve') response.resolve(ok({private: 'late response'}));
    else response.reject(new Error('/private/late-response'));
    expect(await pending).toEqual({state: 'SESSION_CHANGED'});
    expect(delivered).toEqual({ok: false, status: 0, error: 'SESSION_CHANGED'});
    expect(f.controller.getStatus()).toEqual(signedOut);
  });

  it('stale factory transport cannot issue another private HTTP request after logout', async () => {
    const f = fixture(); let transport!: {requestDevice(input: unknown): Promise<ApiResult>};
    f.state.prepareHandler = async (_session, _retry, client) => {transport = client; return ready;};
    expect(await f.controller.prepare()).toEqual(ready);
    await f.controller.requestApi(logout);
    expect(await transport.requestDevice({operation: 'devices.complete', payload: {}})).toMatchObject({ok: false});
    expect(f.state.privateCalls).toEqual([]);
  });

  it.each([ok({authenticated: false}), unauthorized()])('unauthenticated session observations produce SIGNED_OUT, never a coordinator call', async response => {
    const f = fixture(); f.state.publicHandler = async () => response;
    expect(await f.controller.prepare()).toEqual(signedOut);
    expect(f.controller.getStatus()).toEqual(signedOut);
    expect(f.state.prepares).toEqual([]);
  });

  it.each([undefined, null, {}, {authenticated: 'true', user_id: 'owner'}, {authenticated: true},
    ...['', ' ', ' padded', 'trailing ', '\0', '\n', '\ud800', '\udfff', '字'.repeat(257)].map(user_id => ({authenticated: true, user_id})),
    {authenticated: true, user_id: 1},
  ])('invalid authentication data %# cannot provide an identity', async data => {
    const f = fixture(); f.state.publicHandler = async () => ok(data);
    expect(await f.controller.prepare()).toEqual(failed);
    expect(f.state.prepares).toEqual([]);
  });

  it('accepts a canonical 256-code-point user identifier from the trusted service', async () => {
    const f = fixture(); f.state.publicHandler = async () => auth('😀'.repeat(256));
    expect(await f.controller.prepare()).toEqual(ready);
    expect(f.state.prepares[0].session.userId).toBe('😀'.repeat(256));
  });

  it.each([
    {authenticated: true, user_id: 'TEST-owner', tenant_id: 'extra'},
    {authenticated: true, user_id: 'TEST-owner', privateKey: 'extra'},
    {authenticated: false, user_id: 'TEST-owner'},
    {authenticated: false, privateKey: 'extra'},
  ])('rejects additional session response fields instead of silently discarding them %#', async data => {
    const f = fixture(); f.state.publicHandler = async () => ok(data);
    expect(await f.controller.prepare()).toEqual(failed);
    expect(f.controller.getStatus()).toEqual(failed);
    expect(f.state.prepares).toEqual([]);
  });

  it('does not forward a coordinator READY with a version beyond the server range', async () => {
    const f = fixture(); f.state.prepareHandler = async () => ({...ready, credentialVersion: 2_147_483_648});
    expect(await f.controller.prepare()).toEqual(failed);
    expect(f.controller.getStatus()).toEqual(failed);
  });

  it.each(['SERVICE_NOT_CONFIGURED', 'SERVICE_UNAVAILABLE'])('maps %s to a narrow unavailable status', async error => {
    const f = fixture(); f.state.publicHandler = async () => ({ok: false, status: 0, error});
    expect(await f.controller.prepare()).toEqual({state: 'SERVICE_UNAVAILABLE'});
    expect(f.state.prepares).toEqual([]);
  });

  it.each(['session', 'coordinator'] as const)('sanitizes %s exceptions and releases the busy guard', async source => {
    const f = fixture(); expect(await f.controller.prepare()).toEqual(ready);
    if (source === 'session') f.state.publicHandler = async () => {throw new Error('/private/token');};
    else f.state.prepareHandler = async () => {throw new Error('/private/key');};
    expect(await f.controller.prepare()).toEqual(failed);
    expect(f.controller.getStatus()).toEqual(failed);
    f.state.publicHandler = async () => auth(); f.state.prepareHandler = async () => ready;
    expect(await f.controller.prepare()).toEqual(ready);
  });

  it.each([{...ready, privateKey: 'secret'}, {...ready, credentialVersion: 0}, {...ready, deviceId: '../private'}, {state: 'FAILED', error: '/private/path'}, null])('rejects unsafe coordinator result %# rather than forwarding it to IPC', async value => {
    const f = fixture(); f.state.prepareHandler = async () => value as DeviceIdentityResult;
    expect(await f.controller.prepare()).toEqual(failed);
    expect(f.controller.getStatus()).toEqual(failed);
  });

  it('failed or invalid prepare never leaves the previous READY observation in place', async () => {
    const f = fixture(); expect(await f.controller.prepare()).toEqual(ready);
    f.state.prepareHandler = async () => ({state: 'KEY_MISSING'});
    expect(await f.controller.prepare()).toEqual({state: 'KEY_MISSING'});
    expect(f.controller.getStatus()).toEqual({state: 'KEY_MISSING'});
    f.state.prepareHandler = async () => ready; expect(await f.controller.prepare()).toEqual(ready);
    expect(await f.controller.prepare({userId: 'forged'})).toEqual({state: 'INVALID_REQUEST'});
    expect(f.controller.getStatus()).toEqual({state: 'INVALID_REQUEST'});
  });
});
