import {describe, expect, it, vi} from 'vitest';
import {createServiceClient} from '../src/main/serviceClient';
import {candidateBinding, assessmentRequestFixture, verificationRequestFixture, decisionRequestFixture} from './fixtures/candidateReviewApi';

describe('fixed service transport', () => {
  it.each(['user','scope'])('blocks workspace calls after %s identity changes until explicit login',async(change)=>{
    let identity={authenticated:true,user_id:'user-a',account_scope:{id:'scope-a',version:1}};
    const fetch=vi.fn(async()=>Response.json(identity));
    const client=createServiceClient({baseUrl:'https://customer.example',fetch,clearSession:async()=>{}});
    expect(await client.request({operation:'session.get'})).toMatchObject({ok:true});
    identity=change==='user'?{...identity,user_id:'user-b'}:{...identity,account_scope:{id:'scope-b',version:1}};
    expect(await client.request({operation:'session.get'})).toMatchObject({ok:false,error:'SESSION_IDENTITY_CHANGED'});
    expect(await client.request({operation:'profiles.list'})).toMatchObject({ok:false,error:'SESSION_IDENTITY_CHANGED'});
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(await client.request({operation:'session.requestCode',payload:{phone:'19900000001'}})).toMatchObject({ok:true});
    expect(await client.request({operation:'session.loginAccess',payload:{access_code:'YKA-synthetic'}})).toMatchObject({ok:true});
    expect(await client.request({operation:'profiles.list'})).toMatchObject({ok:true});
  });
  it.each([false,true])('persists renewed sessions without clearing existing credentials (failure=%s)',async(fail)=>{
    const clearSession=vi.fn(async()=>{});
    const persistSession=vi.fn(async()=>{if(fail)throw new Error('private-path');});
    const client=createServiceClient({baseUrl:'https://customer.example',clearSession,persistSession,
      fetch:async()=>Response.json({authenticated:true,user_id:'test-user'})});
    expect(await client.request({operation:'session.get'})).toMatchObject(fail
      ? {ok:false,error:'SESSION_PERSIST_FAILED'} : {ok:true});
    expect(persistSession).toHaveBeenCalledOnce();
    expect(clearSession).not.toHaveBeenCalled();
  });
  it('lets an explicit assessment receive a 20-second model response without retrying',async()=>{
    vi.useFakeTimers();
    try{
      const fetch=vi.fn((_url:string,options:RequestInit)=>new Promise<Response>((resolve,reject)=>{
        const timer=setTimeout(()=>resolve(Response.json({kind:'assessment'})),20_000);
        options.signal!.addEventListener('abort',()=>{clearTimeout(timer);reject(new Error('aborted'));},{once:true});
      }));
      const client=createServiceClient({baseUrl:'https://customer.example',fetch,clearSession:async()=>{}});
      const pending=client.request({operation:'candidates.review',payload:assessmentRequestFixture()});
      await vi.advanceTimersByTimeAsync(20_000);
      expect(await pending).toMatchObject({ok:true,data:{kind:'assessment'}});
      expect(fetch).toHaveBeenCalledOnce();
    }finally{vi.useRealTimers();}
  });
  it.each([
    ['assessment', {operation:'candidates.review',payload:assessmentRequestFixture()},75_000],
    ['human inclusion', {operation:'candidates.review',payload:decisionRequestFixture()},12_000],
    ['receipt read', {operation:'candidates.request',payload:{requestId:'TEST:assessment'}},12_000],
  ])('keeps %s bounded with no automatic retry',async(_name,input,timeout)=>{
    vi.useFakeTimers();
    try{
      const fetch=vi.fn((_url:string,options:RequestInit)=>new Promise<Response>((_resolve,reject)=>{
        options.signal!.addEventListener('abort',()=>reject(new Error('aborted')),{once:true});
      }));
      const client=createServiceClient({baseUrl:'https://customer.example',fetch,clearSession:async()=>{}});
      let settled=false;
      const pending=client.request(input).then(value=>{settled=true;return value;});
      await vi.advanceTimersByTimeAsync(timeout-1);expect(settled).toBe(false);
      await vi.advanceTimersByTimeAsync(1);
      expect(await pending).toMatchObject({ok:false,error:'SERVICE_TIMEOUT'});
      expect(fetch).toHaveBeenCalledOnce();
    }finally{vi.useRealTimers();}
  });
  it('awaits encrypted session persistence after authentication and clears stale credentials first',async()=>{
    const order:string[]=[];
    const client=createServiceClient({baseUrl:'https://customer.example',
      beforeAuthentication:async()=>{order.push('clear-old');},
      fetch:async()=>{order.push('login');return Response.json({authenticated:true,user_id:'test-user'});},
      persistSession:async()=>{order.push('persist');},clearSession:async()=>{order.push('clear');}});
    expect(await client.request({operation:'session.loginAccess',payload:{access_code:'YKA-synthetic'}})).toMatchObject({ok:true});
    expect(order).toEqual(['clear-old','login','persist']);
  });
  it('fails closed if the new session cannot be persisted',async()=>{
    const clearSession=vi.fn(async()=>{});
    const client=createServiceClient({baseUrl:'https://customer.example',clearSession,
      fetch:async()=>Response.json({authenticated:true,user_id:'test-user'}),
      persistSession:async()=>{throw new Error('private-path');}});
    expect(await client.request({operation:'session.loginAccess',payload:{access_code:'YKA-synthetic'}})).toMatchObject({ok:false,error:'SESSION_PERSIST_FAILED'});
    expect(clearSession).toHaveBeenCalledOnce();
  });
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
