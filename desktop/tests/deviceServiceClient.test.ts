import {afterEach, describe, expect, it, vi} from 'vitest';
import {createServiceClient} from '../src/main/serviceClient';
import {validatedDeviceOperation} from '../src/main/deviceServicePolicy';

const origin = 'https://customer.example';
const requestId = '11111111-2222-4333-8444-555555555555';
const deviceId = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const challengeId = '12345678-1234-4234-8234-123456789abc';
const publicKey = 'A'.repeat(43);
const signature = 'A'.repeat(86);
const bind = {request_id: requestId, operation: 'BIND', expected_credential_version: 0, public_key: publicKey};
const register = {operation: 'devices.register', payload: {request_id: requestId, device_label: '  办公电脑  '}};
const registration = {operation: 'devices.registration', payload: {request_id: requestId}};
const challenge = {operation: 'devices.challenge', payload: {device_id: deviceId, request: bind}};
const complete = {operation: 'devices.complete', payload: {device_id: deviceId, challenge_id: challengeId, proof: {signature}}};
const routes = [
  {input: register, path: '/api/ui/device-registrations', method: 'POST', body: {request_id: requestId, device_label: '办公电脑'}},
  {input: registration, path: `/api/ui/device-registration-requests/${requestId}`, method: 'GET', body: undefined},
  {input: {operation: 'devices.identity', payload: {device_id: deviceId}}, path: `/api/ui/devices/${deviceId}/identity`, method: 'GET', body: undefined},
  {input: challenge, path: `/api/ui/devices/${deviceId}/key-challenges`, method: 'POST', body: bind},
  {input: complete, path: `/api/ui/devices/${deviceId}/key-challenges/${challengeId}/complete`, method: 'POST', body: {signature, previous_signature: null}},
  {input: {operation: 'devices.receipt', payload: {request_id: requestId}}, path: `/api/ui/device-key-requests/${requestId}`, method: 'GET', body: undefined},
] as const;

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>(done => {resolve = done;});
  return {promise, resolve};
}

afterEach(() => vi.useRealTimers());

describe('private fixed device service transport', () => {
  it.each(routes)('routes $input.operation with exact body and shared authentication safeguards', async ({input, path, method, body}) => {
    const responseData = {transport_test: true};
    const fetch = vi.fn(async () => Response.json(responseData, {status: method === 'POST' ? 201 : 200}));
    const client = createServiceClient({baseUrl: origin, fetch, clearSession: async () => {}});
    expect(validatedDeviceOperation(input)).toEqual({path, method, logout: false, ...(body === undefined ? {} : {body: JSON.stringify(body)})});
    expect(await client.requestDevice(input)).toEqual({ok: true, status: method === 'POST' ? 201 : 200, data: responseData});
    expect(fetch).toHaveBeenCalledExactlyOnceWith(origin + path, {
      method, body: body === undefined ? undefined : JSON.stringify(body),
      headers: {Accept: 'application/json', Origin: origin, ...(body === undefined ? {} : {'Content-Type': 'application/json'})},
      credentials: 'include', redirect: 'manual', cache: 'no-store', signal: expect.any(AbortSignal),
    });
  });

  it('accepts PROVE with explicit null public key and never serializes the routing envelope', async () => {
    const request = {...bind, operation: 'PROVE', expected_credential_version: 1, public_key: null};
    const fetch = vi.fn(async () => Response.json({}));
    const client = createServiceClient({baseUrl: origin, fetch, clearSession: async () => {}});
    expect(await client.requestDevice({...challenge, payload: {device_id: deviceId, request}})).toMatchObject({ok: true});
    expect(fetch).toHaveBeenCalledWith(origin + routes[3].path, expect.objectContaining({body: JSON.stringify(request)}));
  });

  it('keeps all six device operations outside the renderer/public API whitelist', async () => {
    const fetch = vi.fn();
    const client = createServiceClient({baseUrl: origin, fetch, clearSession: async () => {}});
    for (const {input} of routes) {
      expect(await client.request(input)).toEqual({ok: false, status: 0, error: 'INVALID_API_REQUEST'});
    }
    expect(await client.requestDevice({operation: 'session.logout'})).toMatchObject({error: 'INVALID_API_REQUEST'});
    expect(fetch).not.toHaveBeenCalled();
  });

  const invalidInputs: unknown[] = [
    null, [], 'devices.register', {}, {operation: 'devices.register'}, {operation: 'devices.register', payload: null},
    {operation: 'https://other.example', payload: {}},
    ...routes.flatMap(({input}) => [
      {...input, url: 'https://other.example'}, {...input, headers: {Cookie: 'forged'}},
      {...input, payload: {...input.payload, owner_user_id: 'forged'}},
      {...input, payload: {...input.payload, tenant_id: 'forged'}},
      {...input, payload: {...input.payload, url: '/arbitrary'}},
      {...input, payload: []},
    ]),
    ...['../other', deviceId.toUpperCase(), '', 3, null].flatMap(id => [
      {...register, payload: {...register.payload, request_id: id}},
      {...registration, payload: {request_id: id}},
      {operation: 'devices.receipt', payload: {request_id: id}},
      {operation: 'devices.identity', payload: {device_id: id}},
      {...challenge, payload: {...challenge.payload, device_id: id}},
      {...challenge, payload: {...challenge.payload, request: {...bind, request_id: id}}},
      {...complete, payload: {...complete.payload, device_id: id}},
      {...complete, payload: {...complete.payload, challenge_id: id}},
    ]),
    ...['', '   ', '\0', '\ud800', '\udfff', '字'.repeat(129), 12, true, null].map(device_label => ({...register, payload: {request_id: requestId, device_label}})),
    ...[{owner_user_id: 'forged'}, {headers: {}}, {operation: 'ROTATE'}, {expected_credential_version: true}, {expected_credential_version: '0'}, {expected_credential_version: 1}, {public_key: null}, {public_key: publicKey + '='}, {public_key: 'A'.repeat(42) + 'B'}].map(change => ({...challenge, payload: {...challenge.payload, request: {...bind, ...change}}})),
    ...[{signature: signature + '='}, {signature: 'A'.repeat(85) + 'B'}, {signature: true}, {previous_signature: signature}, {owner_user_id: 'forged'}, {signing_payload: '{}'}].map(change => ({...complete, payload: {...complete.payload, proof: {signature, ...change}}})),
    {...challenge, payload: {...challenge.payload, request: null}},
    {...complete, payload: {...complete.payload, proof: null}},
  ];
  it.each(invalidInputs.map((input, index) => ({input, index})))('rejects strict invalid input $index before fetching', async ({input}) => {
    const fetch = vi.fn();
    const client = createServiceClient({baseUrl: origin, fetch, clearSession: async () => {}});
    expect(validatedDeviceOperation(input)).toBeNull();
    expect(await client.requestDevice(input)).toEqual({ok: false, status: 0, error: 'INVALID_API_REQUEST'});
    expect(fetch).not.toHaveBeenCalled();
  });

  it('uses the same login/device/logout queue and clears cookies after device and logout failures', async () => {
    const release = deferred();
    const order: string[] = [];
    const client = createServiceClient({baseUrl: origin, fetch: async (url, init) => {
      order.push(`${init.method} ${new URL(url).pathname}`);
      if (init.method === 'POST' && url.endsWith('/session')) {await release.promise; return Response.json({});}
      throw new Error('private failure');
    }, clearSession: async () => {order.push('clear');}});
    const login = client.request({operation: 'session.login', payload: {token: 'synthetic-token'}});
    const device = client.requestDevice(register);
    const logout = client.request({operation: 'session.logout'});
    await Promise.resolve();
    expect(order).toEqual(['POST /api/ui/session']);
    release.resolve();
    expect(await login).toMatchObject({ok: true});
    expect(await device).toEqual({ok: false, status: 0, error: 'SERVICE_UNAVAILABLE'});
    expect(await logout).toEqual({ok: false, status: 0, error: 'SERVICE_UNAVAILABLE'});
    expect(order).toEqual(['POST /api/ui/session', 'POST /api/ui/device-registrations', 'DELETE /api/ui/session', 'clear']);
  });

  it('shares a 16-pending cap across public and device requests and releases capacity', async () => {
    const release = deferred();
    const fetch = vi.fn(async () => {await release.promise; return Response.json({});});
    const client = createServiceClient({baseUrl: origin, fetch, clearSession: async () => {}});
    const pending = Array.from({length: 16}, (_, i) => i % 2 ? client.requestDevice(registration) : client.request({operation: 'session.get'}));
    expect(await client.requestDevice(registration)).toEqual({ok: false, status: 0, error: 'SERVICE_BUSY'});
    expect(await client.request({operation: 'session.get'})).toEqual({ok: false, status: 0, error: 'SERVICE_BUSY'});
    expect(await client.requestDevice({operation: 'bad'})).toMatchObject({error: 'INVALID_API_REQUEST'});
    expect(fetch).toHaveBeenCalledTimes(1);
    release.resolve();
    expect((await Promise.all(pending)).every(result => result.ok)).toBe(true);
    expect(await client.requestDevice(registration)).toMatchObject({ok: true});
    expect(fetch).toHaveBeenCalledTimes(17);
  });

  it('snapshots nested bodies and route UUIDs before enqueue so later input mutation is inert', async () => {
    const release = deferred();
    const fetch = vi.fn(async () => {await release.promise; return Response.json({});});
    const client = createServiceClient({baseUrl: origin, fetch, clearSession: async () => {}});
    const login = client.request({operation: 'session.login', payload: {token: 'synthetic-token'}});
    const inputs = routes.map(({input}) => structuredClone(input));
    const pending = inputs.map(input => client.requestDevice(input));
    for (const input of inputs) {
      Object.assign(input.payload, {request_id: challengeId, device_id: requestId, challenge_id: deviceId, device_label: 'changed'});
      if ('request' in input.payload) Object.assign(input.payload.request, {operation: 'ROTATE', public_key: 'changed'});
      if ('proof' in input.payload) Object.assign(input.payload.proof, {signature: 'changed'});
    }
    release.resolve();
    await login;
    expect((await Promise.all(pending)).every(result => result.ok)).toBe(true);
    for (const [index, {path, method, body}] of routes.entries()) {
      expect(fetch.mock.calls[index + 1]).toEqual([origin + path, expect.objectContaining({method, body: body === undefined ? undefined : JSON.stringify(body)})]);
    }
  });

  it('does not fetch when the service is not configured', async () => {
    const fetch = vi.fn();
    const client = createServiceClient({baseUrl: null, fetch, clearSession: async () => {}});
    expect(await client.requestDevice(register)).toEqual({ok: false, status: 0, error: 'SERVICE_NOT_CONFIGURED'});
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each([
    {name: 'redirect', response: () => new Response('', {status: 302}), error: 'SERVICE_REDIRECT_REJECTED', status: 302},
    {name: 'non-JSON', response: () => new Response('private HTML'), error: 'SERVICE_NON_JSON_RESPONSE', status: 0},
    {name: 'invalid JSON', response: () => new Response('{', {headers: {'Content-Type': 'application/json'}}), error: 'SERVICE_INVALID_RESPONSE', status: 0},
    {name: 'oversized stream', response: () => Response.json({private: 'a'.repeat(200)}), error: 'SERVICE_RESPONSE_TOO_LARGE', status: 0},
    {name: 'oversized declared length', response: () => new Response('{}', {headers: {'Content-Type': 'application/json', 'Content-Length': '200'}}), error: 'SERVICE_RESPONSE_TOO_LARGE', status: 0},
    {name: 'safe service error', response: () => Response.json({detail: {code: 'request_conflict', message: 'private'}}, {status: 409}), error: 'request_conflict', status: 409},
    {name: 'unsafe service error', response: () => Response.json({detail: {code: 'private/path', message: 'private'}}, {status: 503}), error: 'HTTP_503', status: 503},
    {name: 'unknown outcome', response: () => Response.json({detail: {code: 'registration_outcome_unknown'}}, {status: 503}), error: 'registration_outcome_unknown', status: 503},
  ])('inherits $name protection with one POST and no automatic retry/recovery', async ({response, error, status}) => {
    const fetch = vi.fn(async () => response());
    const client = createServiceClient({baseUrl: origin, fetch, clearSession: async () => {}, maxResponseBytes: 120});
    expect(await client.requestDevice(register)).toEqual({ok: false, status, error});
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('inherits abort timeout and recovers only through an explicit original-request GET', async () => {
    vi.useFakeTimers();
    const started = deferred();
    const fetch = vi.fn(async (_url: string, init: RequestInit) => {
      if (init.method === 'GET') return Response.json({});
      started.resolve();
      return new Promise<Response>((_resolve, reject) => init.signal!.addEventListener('abort', () => reject(new Error('private timeout'))));
    });
    const client = createServiceClient({baseUrl: origin, fetch, clearSession: async () => {}, timeoutMs: 25});
    const pending = client.requestDevice(register);
    await Promise.resolve();
    expect(fetch).toHaveBeenCalledTimes(1);
    await started.promise;
    await vi.advanceTimersByTimeAsync(25);
    expect(await pending).toEqual({ok: false, status: 0, error: 'SERVICE_TIMEOUT'});
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(await client.requestDevice(registration)).toMatchObject({ok: true});
    expect(fetch).toHaveBeenLastCalledWith(origin + routes[1].path, expect.objectContaining({method: 'GET', body: undefined}));
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
