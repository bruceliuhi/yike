import {describe, expect, it, vi} from 'vitest';
import {createServiceClient} from '../src/main/serviceClient';
import {candidateBinding, assessmentRequestFixture, verificationRequestFixture} from './fixtures/candidateReviewApi';

describe('fixed service transport', () => {
  it('reads raw candidate evidence by a strict candidate UUID without caller URLs', async () => {
    const fetch = vi.fn(async () => Response.json({}));
    const client = createServiceClient({baseUrl:'https://customer.example',fetch,clearSession:async()=>{}});
    expect(await client.request({operation:'candidates.rawEvidence',payload:{candidateId:candidateBinding.candidateId}})).toMatchObject({ok:true});
    expect(fetch).toHaveBeenCalledWith(`https://customer.example/api/ui/raw-candidates/${candidateBinding.candidateId}`,expect.objectContaining({method:'GET'}));
    for (const payload of [{candidateId:'../other'},{candidateId:candidateBinding.candidateId,url:'https://other.example'},{candidateId:candidateBinding.candidateId,tenantId:'other'}]) {
      expect(await client.request({operation:'candidates.rawEvidence',payload})).toMatchObject({ok:false,error:'INVALID_API_REQUEST'});
    }
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('routes candidate operations through the same fixed authenticated origin', async () => {
    const fetch = vi.fn(async () => Response.json({}));
    const client = createServiceClient({baseUrl:'https://customer.example',fetch,clearSession:async()=>{}});
    const query = {ids:[candidateBinding.candidateId],reviewRequestId:'TEST:decision',page:1,pageSize:1};
    for (const input of [
      {operation:'candidates.list',payload:query},
      {operation:'candidates.review',payload:assessmentRequestFixture()},
      {operation:'candidates.verifySource',payload:verificationRequestFixture()},
      {operation:'candidates.request',payload:{requestId:'TEST:decision'}},
    ]) expect(await client.request(input)).toMatchObject({ok:true});
    const calls = fetch.mock.calls as unknown as [string,RequestInit][];
    expect(calls.map(([url,init])=>[new URL(url).pathname,init.method])).toEqual([
      ['/api/ui/candidates','GET'],['/api/ui/candidate-reviews','POST'],['/api/ui/candidate-source-verifications','POST'],['/api/ui/candidate-review-requests/TEST%3Adecision','GET']
    ]);
    expect(Object.fromEntries(new URL(calls[0][0]).searchParams)).toEqual({...query,ids:candidateBinding.candidateId,page:'1',pageSize:'1'});
    expect(calls[1][1].body).toBe(JSON.stringify(assessmentRequestFixture()));
    for (const [,init] of calls) expect(init).toMatchObject({credentials:'include',redirect:'manual',headers:expect.objectContaining({Origin:'https://customer.example'})});
    const count = fetch.mock.calls.length;
    for (const input of [
      {operation:'candidates.list',payload:{platform:'arbitrary'}},
      {operation:'candidates.review',payload:{...assessmentRequestFixture(),tenant:'forged'}},
      {operation:'candidates.verifySource',payload:{...verificationRequestFixture(),checkedBy:'forged'}},
      {operation:'candidates.request',payload:{requestId:'../wrong'}}
    ]) expect(await client.request(input)).toMatchObject({ok:false,error:'INVALID_API_REQUEST'});
    expect(fetch).toHaveBeenCalledTimes(count);
  });
  it('does not request anything without service config or with an invalid operation', async () => {
    const fetch = vi.fn();
    const client = createServiceClient({baseUrl: null, fetch, clearSession: async () => {}});
    expect(await client.request({operation: 'profiles.list'})).toMatchObject({ok: false, error: 'SERVICE_NOT_CONFIGURED'});
    expect(await client.request({operation: 'arbitrary.url'})).toMatchObject({ok: false, error: 'INVALID_API_REQUEST'});
    expect(fetch).not.toHaveBeenCalled();
  });

  it('uses the fixed origin, session cookies and no renderer-supplied headers', async () => {
    const fetch = vi.fn(async () => Response.json({items: []}));
    const client = createServiceClient({baseUrl: 'https://customer.example', fetch, clearSession: async () => {}});
    expect(await client.request({operation: 'profiles.list'})).toEqual({ok: true, status: 200, data: {items: []}});
    expect(fetch).toHaveBeenCalledWith('https://customer.example/api/ui/profiles', expect.objectContaining({
      method: 'GET', credentials: 'include', redirect: 'manual',
      headers: {Accept: 'application/json', Origin: 'https://customer.example'}
    }));
  });

  it('rejects redirects, HTML, oversized streams and surfaces only safe error codes', async () => {
    const responses = [
      new Response('', {status: 302, headers: {Location: 'https://evil'}}),
      new Response('<html>error</html>', {headers: {'Content-Type': 'text/html'}}),
      Response.json({content: 'x'.repeat(100)}),
      Response.json({detail: {code: 'origin_forbidden', message: '/private/path'}}, {status: 403})
    ];
    const client = createServiceClient({baseUrl: 'https://customer.example', fetch: async () => responses.shift()!, clearSession: async () => {}, maxResponseBytes: 90});
    expect(await client.request({operation: 'session.get'})).toMatchObject({error: 'SERVICE_REDIRECT_REJECTED'});
    expect(await client.request({operation: 'session.get'})).toMatchObject({error: 'SERVICE_NON_JSON_RESPONSE'});
    expect(await client.request({operation: 'session.get'})).toMatchObject({error: 'SERVICE_RESPONSE_TOO_LARGE'});
    expect(await client.request({operation: 'session.get'})).toEqual({ok: false, status: 403, error: 'origin_forbidden'});
  });

  it('orders login before logout and clears local credentials even when logout fails', async () => {
    const order: string[] = [];
    let release!: () => void;
    const pending = new Promise<void>(resolve => {release = resolve;});
    const client = createServiceClient({
      baseUrl: 'https://customer.example',
      fetch: async (_url, init) => {
        order.push(init.method!);
        if (init.method === 'POST') {await pending; return Response.json({authenticated: true});}
        throw new Error('offline');
      },
      clearSession: async () => {order.push('clear');}
    });
    const login = client.request({operation: 'session.login', payload: {token: 'short-lived-token'}});
    const logout = client.request({operation: 'session.logout'});
    await Promise.resolve(); expect(order).toEqual(['POST']);
    release(); await login;
    expect(await logout).toMatchObject({ok: false, error: 'SERVICE_UNAVAILABLE'});
    expect(order).toEqual(['POST', 'DELETE', 'clear']);
  });
});
