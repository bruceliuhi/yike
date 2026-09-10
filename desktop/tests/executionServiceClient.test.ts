import {describe, expect, it, vi} from 'vitest';
import {createServiceClient} from '../src/main/serviceClient';
import {validatedExecutionOperation} from '../src/main/executionServicePolicy';

const id = '00000000-0000-0000-0000-000000000001';
const operation = {schema_version: 'execution-runtime-v1', request_id: id, device_id: id,
  credential_version: 1, operation: 'CANCEL', task_id: id, profile_version_id: null,
  strategy_version_id: null, configuration_sha256: null, targets: null,
  platform_run_id: null, lease_id: null, execution_generation: null};
const routes = [
  {operation: 'execution.prepare', payload: {request: operation}, path: '/api/ui/execution-signing-payload', method: 'POST'},
  {operation: 'execution.apply', payload: {request: operation, signature: 'A'.repeat(86)}, path: '/api/ui/execution-operations', method: 'POST'},
  {operation: 'execution.receipt', payload: {request_id: id}, path: `/api/ui/execution-operations/${id}`, method: 'GET'},
  {operation: 'execution.task', payload: {task_id: id}, path: `/api/ui/execution-tasks/${id}`, method: 'GET'},
] as const;

describe('main-only execution transport', () => {
  it.each(routes)('routes $operation without public IPC access', async ({path, method, ...input}) => {
    const fetch = vi.fn(async () => Response.json({}));
    const client = createServiceClient({baseUrl: 'https://service.example', fetch, clearSession: async () => {}});
    const routed = validatedExecutionOperation(input);
    expect(routed).toMatchObject({path, method, logout: false});
    const body = routed?.body;
    expect(body === undefined ? undefined : JSON.parse(body)).toEqual(method === 'POST' ? input.payload : undefined);
    expect(await client.request(input)).toMatchObject({error: 'INVALID_API_REQUEST'});
    expect(await client.requestDevice(input)).toMatchObject({error: 'INVALID_API_REQUEST'});
    expect(await client.requestExecution(input)).toMatchObject({ok: true});
    expect(fetch).toHaveBeenCalledExactlyOnceWith('https://service.example' + path, expect.objectContaining({
      method, body, credentials: 'include', redirect: 'manual', cache: 'no-store',
      headers: {Accept: 'application/json', Origin: 'https://service.example', ...(body ? {'Content-Type': 'application/json'} : {})},
    }));
  });

  it.each([
    {operation: 'session.logout'}, {operation: 'execution.task', payload: {task_id: '../escape'}},
    {operation: 'execution.receipt', payload: {request_id: id, tenant_id: 'forged'}},
    {operation: 'execution.prepare', payload: {request: operation, signing_payload: '{}'}},
    {operation: 'execution.apply', payload: {request: operation, signature: 'A'.repeat(85) + 'B'}},
    {operation: 'execution.apply', payload: {request: {...operation, targets: []}, signature: 'A'.repeat(86)}},
    {...routes[0], headers: {Cookie: 'forged'}}, null,
  ])('rejects invalid private input before fetching %#', async input => {
    const fetch = vi.fn();
    const client = createServiceClient({baseUrl: 'https://service.example', fetch, clearSession: async () => {}});
    expect(await client.requestExecution(input)).toMatchObject({error: 'INVALID_API_REQUEST'});
    expect(fetch).not.toHaveBeenCalled();
  });

  it('snapshots requests synchronously and shares session/device queue and capacity', async () => {
    let release!: () => void;
    const gate = new Promise<void>(resolve => {release = resolve;});
    const calls: Array<{url: string; body?: BodyInit | null}> = [];
    const client = createServiceClient({baseUrl: 'https://service.example', fetch: async (url, init) => {
      calls.push({url, body: init.body}); await gate; return Response.json({});
    }, clearSession: async () => {}});
    const login = client.request({operation: 'session.login', payload: {token: 'test'}});
    const mutable = structuredClone(routes[0]);
    const pending = client.requestExecution({operation: mutable.operation, payload: mutable.payload});
    mutable.payload.request.credential_version = 2;
    const remaining = Array.from({length: 14}, () => client.requestDevice({operation: 'devices.identity', payload: {device_id: id}}));
    expect(await client.requestExecution({operation: routes[2].operation, payload: routes[2].payload})).toMatchObject({error: 'SERVICE_BUSY'});
    await Promise.resolve();
    expect(calls).toHaveLength(1);
    release(); await Promise.all([login, pending, ...remaining]);
    expect(JSON.parse(calls[1].body as string).request.credential_version).toBe(1);
  });

  it('does not retry an unknown POST; original GET remains explicit and 404 is preserved', async () => {
    const fetch = vi.fn(async (_url: string, init: RequestInit) => {
      if (init.method === 'POST') throw new Error('private details');
      return Response.json({detail: {code: 'not_found'}}, {status: 404});
    });
    const client = createServiceClient({baseUrl: 'https://service.example', fetch, clearSession: async () => {}});
    expect(await client.requestExecution({operation: routes[1].operation, payload: routes[1].payload})).toEqual({ok: false, status: 0, error: 'SERVICE_UNAVAILABLE'});
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(await client.requestExecution({operation: routes[2].operation, payload: routes[2].payload})).toEqual({ok: false, status: 404, error: 'not_found'});
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
