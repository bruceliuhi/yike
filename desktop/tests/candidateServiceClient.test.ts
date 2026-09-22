import {describe, expect, it, vi} from 'vitest';
import {createServiceClient} from '../src/main/serviceClient';

const id = '00000000-0000-0000-0000-000000000001';
function batch() {
  return {schema_version: 'candidate-upload-v1', request_id: 'batch:original_1', platform: 'PUBLIC_WEB',
    profile_version_id: 'profile-1', strategy_version_id: 'strategy-1', execution: {
      device_id: id, task_id: id, run_id: id, platform_run_id: id, lease_id: id,
      credential_version: 1, execution_generation: 1, access_mode: 'PUBLIC_ANONYMOUS', connection_id: null, connection_version: null,
    }, records: [{kind: 'PAGE', external_source_id: null, external_comment_id: null,
      public_url: 'https://example.com/item', title: null, author_public_id: null,
      body: '  原文 e\u0301😀\n', published_at: null, observed_at: '2026-09-10T00:00:00Z', parent: null,
      collector_version: 'collector-1', normalizer_version: 'normalizer-1', query: null}]};
}
const signature = 'A'.repeat(86);
const receipt = {operation: 'candidate.receipt', payload: {platform_run_id: id, request_id: 'batch:original_1'}};

describe('main-only candidate transport', () => {
  it.each([
    ['candidate.prepare', '/api/ui/candidate-submission-signing-payload', 'POST'],
    ['candidate.apply', '/api/ui/candidate-batches', 'POST'],
    ['candidate.receipt', `/api/ui/candidate-batches/${id}/batch%3Aoriginal_1`, 'GET'],
  ])('routes %s only through the private channel', async (operation, path, method) => {
    const fetch = vi.fn(async () => Response.json({}));
    const client = createServiceClient({baseUrl: 'https://service.example', fetch, clearSession: async () => {}});
    const payload = operation === 'candidate.receipt' ? receipt.payload : {batch: batch(), ...(operation === 'candidate.apply' ? {signature} : {})};
    const input = {operation, payload};
    for (const request of [client.request, client.requestDevice, client.requestExecution]) {
      expect(await request(input)).toMatchObject({error: 'INVALID_API_REQUEST'});
    }
    expect(await client.requestCandidate(input)).toMatchObject({ok: true});
    expect(fetch).toHaveBeenCalledExactlyOnceWith('https://service.example' + path, expect.objectContaining({
      method, body: method === 'POST' ? JSON.stringify(payload) : undefined,
      credentials: 'include', redirect: 'manual', cache: 'no-store',
    }));
  });

  it.each([
    null, {operation: 'session.logout'}, {operation: 'execution.receipt', payload: {request_id: id}},
    {operation: 'candidate.receipt', payload: {...receipt.payload, platform_run_id: 'opaque'}},
    {operation: 'candidate.receipt', payload: {...receipt.payload, request_id: '../escape'}},
    {operation: 'candidate.receipt', payload: {...receipt.payload, request_id: 'a'.repeat(129)}},
    {operation: 'candidate.receipt', payload: {...receipt.payload, tenant_id: 'forged'}},
    {operation: 'candidate.prepare', payload: {batch: batch(), signing_payload: '{}'}},
    {operation: 'candidate.apply', payload: {batch: batch(), signature: 'A'.repeat(85) + 'B'}},
    {operation: 'candidate.apply', payload: {batch: {...batch(), records: []}, signature, headers: {Cookie: 'forged'}}},
    {operation: 'candidate.prepare', payload: {batch: {...batch(), tenant_id: 'forged'}}},
    {...receipt, url: 'https://elsewhere.example'},
  ])('rejects malformed input before fetch %#', async input => {
    const fetch = vi.fn();
    const client = createServiceClient({baseUrl: 'https://service.example', fetch, clearSession: async () => {}});
    expect(await client.requestCandidate(input)).toMatchObject({error: 'INVALID_API_REQUEST'});
    expect(fetch).not.toHaveBeenCalled();
  });

  it('shares the 16-place queue with session/device/execution and snapshots the entire batch', async () => {
    let release!: () => void;
    const gate = new Promise<void>(resolve => {release = resolve;});
    const calls: Array<{url: string; body?: BodyInit | null}> = [];
    const client = createServiceClient({baseUrl: 'https://service.example', fetch: async (url, init) => {
      calls.push({url, body: init.body}); await gate;
      return url.endsWith('/api/ui/session') ? Response.json({authenticated:true,user_id:'test-user'}) : Response.json({});
    }, clearSession: async () => {}});
    const login = client.request({operation: 'session.login', payload: {token: 'test'}});
    const original = batch();
    const upload = client.requestCandidate({operation: 'candidate.apply', payload: {batch: original, signature}});
    original.records[0].body = 'mutated'; original.execution.credential_version = 2;
    const execution = client.requestExecution({operation: 'execution.receipt', payload: {request_id: id}});
    const devices = Array.from({length: 13}, () => client.requestDevice({operation: 'devices.identity', payload: {device_id: id}}));
    expect(await client.requestCandidate(receipt)).toMatchObject({error: 'SERVICE_BUSY'});
    await Promise.resolve(); expect(calls).toHaveLength(1);
    release(); await Promise.all([login, upload, execution, ...devices]);
    expect(JSON.parse(calls[1].body as string)).toEqual({batch: batch(), signature});
  });

  it('bounds actual UTF-8 envelope bytes including signature without truncation or splitting', async () => {
    const fetch = vi.fn(async () => Response.json({}));
    const client = createServiceClient({baseUrl: 'https://service.example', fetch, clearSession: async () => {}});
    const large = batch();
    large.records = Array.from({length: 100}, () => ({...batch().records[0], body: '😀'.repeat(10000)}));
    // Fill the final body to put prepare exactly at 4 MiB; adding signature crosses the boundary.
    const initial = Buffer.byteLength(JSON.stringify({batch: large}), 'utf8');
    const remaining = 4 * 1024 * 1024 - initial;
    expect(remaining).toBeGreaterThan(0);
    for (const record of large.records) {
      const add = Math.min(10000, 4 * 1024 * 1024 - Buffer.byteLength(JSON.stringify({batch: large}), 'utf8'));
      record.body += 'a'.repeat(add);
    }
    expect(Buffer.byteLength(JSON.stringify({batch: large}), 'utf8')).toBe(4 * 1024 * 1024);
    expect(await client.requestCandidate({operation: 'candidate.prepare', payload: {batch: large}})).toMatchObject({ok: true});
    expect(await client.requestCandidate({operation: 'candidate.apply', payload: {batch: large, signature}})).toMatchObject({error: 'INVALID_API_REQUEST'});
    expect(fetch).toHaveBeenCalledTimes(1);
    large.records[99].body += 'a';
    expect(await client.requestCandidate({operation: 'candidate.prepare', payload: {batch: large}})).toMatchObject({error: 'INVALID_API_REQUEST'});
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('never retries an unknown POST and recovers only by the explicitly supplied original composite key', async () => {
    const fetch = vi.fn(async (_url: string, init: RequestInit) => {
      if (init.method === 'POST') throw new Error('private details');
      return Response.json({detail: {code: 'not_found'}}, {status: 404});
    });
    const client = createServiceClient({baseUrl: 'https://service.example', fetch, clearSession: async () => {}});
    expect(await client.requestCandidate({operation: 'candidate.apply', payload: {batch: batch(), signature}})).toEqual({ok: false, status: 0, error: 'SERVICE_UNAVAILABLE'});
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(await client.requestCandidate(receipt)).toEqual({ok: false, status: 404, error: 'not_found'});
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
