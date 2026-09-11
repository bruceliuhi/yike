import {afterEach, expect, it, vi} from 'vitest';

const module = await import('../src/main/publicCommunityDriver').catch(() => null);
const now = Date.parse('2026-09-11T10:00:00Z');
const id = (n:number) => `00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
function input() {return {snapshot:{profile_version_id:id(1),strategy_version_id:id(2),platforms:['PUBLIC_WEB'],max_records:5,max_runtime_seconds:60,
  configuration:{schema_version:'research-strategy-v1',name:'社区',source:'search',keywords:['AI'],exclusions:['招聘'],links:[],mode:'once',schedule:null,research:null,publicSource:'v2ex-latest-v1'}},
  target:{platform:'PUBLIC_WEB',access_mode:'PUBLIC_ANONYMOUS',connection_id:null,connection_version:null},
  lease:{schema_version:'execution-runtime-v1',operation:'CLAIM',request_id:id(3),task_id:id(4),run_id:id(5),platform_run_id:id(6),status:'RUNNING',stop_confirmed:false,
    lease_id:id(7),execution_generation:1,lease_expires_at:new Date(now+120000).toISOString(),deadline_at:new Date(now+60000).toISOString()},
  maxRecords:5,signal:new AbortController().signal} as any;}
function monitorInput() {const value=input();value.snapshot.configuration.mode='monitor';value.snapshot.configuration.schedule={kind:'interval',times:[],interval:1,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1};return value;}
const topic=(n=12,body='  AI 系统需求\n保留原文 ')=>({id:n,title:'询问方案',content:body,created:Math.floor(now/1000)-600,
  last_touched:Math.floor(now/1000),deleted:0,member:{id:9},url:`https://www.v2ex.com/t/${n}#reply0`});
function driver(fetcher:typeof fetch) {
  expect(module?.createPublicCommunityDriver).toBeTypeOf('function');
  return module!.createPublicCommunityDriver({fetch:fetcher,now:()=>now});
}
afterEach(()=>{vi.useRealTimers();});
it('preserves original evidence and anonymous identity using one fixed public request',async()=>{
  const fetcher=vi.fn(async()=>new Response(JSON.stringify([topic()]),{headers:{'content-type':'application/json'}}));
  const run=driver(fetcher).start(input());
  const records=await run.completed;await run.stop();
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(fetcher.mock.calls[0]).toMatchObject(['https://www.v2ex.com/api/topics/latest.json',{redirect:'error',credentials:'omit'}]);
  expect(records).toMatchObject([{kind:'PAGE',external_source_id:'12',external_comment_id:null,public_url:'https://www.v2ex.com/t/12',
    body:'  AI 系统需求\n保留原文 ',author_public_id:'9',published_at:'2026-09-11T09:50:00Z',observed_at:'2026-09-11T10:00:00Z',parent:null,query:'AI'}]);
});
it('bounded sampling consumes excluded topics without extending the source budget',async()=>{
  const fetcher=vi.fn(async()=>new Response(JSON.stringify([topic(1,'招聘AI工程师'),topic(2),topic(3)]),{headers:{'content-type':'application/json'}}));
  const run=driver(fetcher).start({...input(),maxRecords:2});
  expect(await run.completed).toMatchObject([{external_source_id:'2'}]);await run.stop();
});
it.each(['account','monitor','links','budget','source','missing_source'])('rejects unsupported %s before networking',async kind=>{
  const fetcher=vi.fn();const value=input();
  if(kind==='account')value.target.connection_id=id(99);
  if(kind==='monitor')value.snapshot.configuration.mode='monitor';
  if(kind==='links')value.snapshot.configuration.links=['https://example.org'];
  if(kind==='budget')value.maxRecords=6;
  if(kind==='source')value.snapshot.configuration.publicSource='other';
  if(kind==='missing_source')delete value.snapshot.configuration.publicSource;
  const run=driver(fetcher).start(value);
  await expect(run.completed).rejects.toThrow('PUBLIC_SOURCE_INVALID_INPUT');await run.stop();expect(fetcher).not.toHaveBeenCalled();
});
it('allows monitor only through the explicit per-start authority while preserving one driver cooldown',async()=>{
  const fetcher=vi.fn(async()=>new Response(JSON.stringify([topic()]),{headers:{'content-type':'application/json'}}));
  const reader=driver(fetcher);
  const denied=reader.start(monitorInput());await expect(denied.completed).rejects.toThrow('PUBLIC_SOURCE_INVALID_INPUT');await denied.stop();
  const allowed=reader.start({...monitorInput(),allowMonitor:true});expect(await allowed.completed).toHaveLength(1);await allowed.stop();
  const second=reader.start({...monitorInput(),allowMonitor:true});await expect(second.completed).rejects.toThrow('PUBLIC_SOURCE_RATE_LIMITED');await second.stop();
  expect(fetcher).toHaveBeenCalledTimes(1);
});
it('uses the same cooldown-bearing driver for later monitor rounds',async()=>{
  let clock=now;const fetcher=vi.fn(async()=>new Response(JSON.stringify([topic()]),{headers:{'content-type':'application/json'}}));
  const reader=module!.createPublicCommunityDriver({fetch:fetcher,now:()=>clock});
  const first=reader.start({...monitorInput(),allowMonitor:true});expect(await first.completed).toHaveLength(1);await first.stop();
  clock+=60000;const next=monitorInput();next.lease.lease_expires_at=new Date(clock+120000).toISOString();next.lease.deadline_at=new Date(clock+60000).toISOString();
  const second=reader.start({...next,allowMonitor:true});expect(await second.completed).toHaveLength(1);await second.stop();
  expect(fetcher).toHaveBeenCalledTimes(2);
});
it('does not let a monitor bypass cooldown established by an earlier once sample on the same driver',async()=>{
  const fetcher=vi.fn(async()=>new Response(JSON.stringify([topic()]),{headers:{'content-type':'application/json'}}));const reader=driver(fetcher);
  const once=reader.start(input());expect(await once.completed).toHaveLength(1);await once.stop();
  const monitor=reader.start({...monitorInput(),allowMonitor:true});await expect(monitor.completed).rejects.toThrow('PUBLIC_SOURCE_RATE_LIMITED');await monitor.stop();
  expect(fetcher).toHaveBeenCalledTimes(1);
});
it('spaces requests to the same public source even after failed fetch, without retry',async()=>{
  const fetcher=vi.fn(async()=>new Response('{}',{status:429,headers:{'content-type':'application/json'}}));
  const reader=driver(fetcher);
  const first=reader.start(input());await expect(first.completed).rejects.toThrow('PUBLIC_SOURCE_FAILED');await first.stop();
  const second=reader.start(input());await expect(second.completed).rejects.toThrow('PUBLIC_SOURCE_RATE_LIMITED');await second.stop();
  expect(fetcher).toHaveBeenCalledTimes(1);
});
it.each([429,302])('HTTP %s never becomes an empty successful result or retries',async status=>{
  const fetcher=vi.fn(async()=>new Response('{}',{status,headers:{'content-type':'application/json'}}));
  const run=driver(fetcher).start(input());await expect(run.completed).rejects.toThrow('PUBLIC_SOURCE_FAILED');await run.stop();expect(fetcher).toHaveBeenCalledTimes(1);
});
it.each(['oversize','foreign_url','future','duplicate','html'])('rejects %s response evidence',async kind=>{
  const value=topic();if(kind==='foreign_url')value.url='https://attacker.invalid/t/12';if(kind==='future')value.created=Math.floor(now/1000)+3600;
  const body=kind==='oversize'?' '.repeat(1048577):JSON.stringify(kind==='duplicate'?[value,value]:[value]);
  const fetcher=vi.fn(async()=>new Response(body,{headers:{'content-type':kind==='html'?'text/html':'application/json'}}));
  const run=driver(fetcher).start(input());await expect(run.completed).rejects.toThrow('PUBLIC_SOURCE_FAILED');await run.stop();
});
it('cancel aborts an in-flight response and waits for it to settle',async()=>{
  let finish!:()=>void;let signal!:AbortSignal;
  const fetcher=vi.fn((_url:any,init:any)=>{signal=init.signal;return new Promise<Response>((_resolve,reject)=>{finish=()=>reject(new Error('aborted'));});});
  const run=driver(fetcher).start(input());await Promise.resolve();
  const completed=expect(run.completed).rejects.toThrow('PUBLIC_SOURCE_CANCELLED');
  const stopped=run.stop();expect(signal.aborted).toBe(true);let done=false;void stopped.then(()=>{done=true;});await Promise.resolve();expect(done).toBe(false);
  finish();await stopped;await completed;
});
it('deadline aborts a stalled response body instead of waiting indefinitely',async()=>{
  vi.useFakeTimers();
  const fetcher=vi.fn(async(_url:any,init:any)=>new Response(new ReadableStream({start(controller){
    init.signal.addEventListener('abort',()=>controller.error(new Error('timeout')),{once:true});
  }}),{headers:{'content-type':'application/json'}}));
  const run=driver(fetcher).start(input());
  const rejected=expect(run.completed).rejects.toThrow('PUBLIC_SOURCE_TIMED_OUT');
  await vi.advanceTimersByTimeAsync(20000);await rejected;await run.stop();
});
