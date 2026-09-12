import {expect,it,vi} from 'vitest';
import {executionOperationSchema} from '../src/shared/executionOperation';
import {executionReceiptSchema,parseExecutionReceipt} from '../src/shared/executionReceipt';
import {validatedExecutionOperation} from '../src/main/executionServicePolicy';
import {createPublicCommunityDriver} from '../src/main/publicCommunityDriver';

const id=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const epoch=Date.parse('2026-09-12T10:00:00Z');
const progress=(round=0)=>({schema_version:'public-sampling-round-v1',plan_id:id(10),source_id:'v2ex-outsourcing-authors-v1',round});
const claim=()=>({schema_version:'execution-runtime-v1',request_id:id(3),operation:'CLAIM',device_id:id(8),credential_version:1,task_id:id(4),platform_run_id:id(6)});
const lease=(now=epoch)=>({schema_version:'execution-runtime-v1',operation:'CLAIM',request_id:id(3),task_id:id(4),run_id:id(5),platform_run_id:id(6),
  status:'RUNNING',stop_confirmed:false,lease_id:id(7),execution_generation:1,lease_expires_at:new Date(now+60000).toISOString(),deadline_at:new Date(now+60000).toISOString()});
function input(round:number|undefined,budget=3,now=epoch):any{return {
  snapshot:{profile_version_id:id(1),strategy_version_id:id(2),platforms:['PUBLIC_WEB'],max_records:budget,max_runtime_seconds:60,
    configuration:{schema_version:'research-strategy-v1',name:'公开需求',source:'search',keywords:['AI'],exclusions:['招聘'],links:[],mode:'monitor',
      schedule:{kind:'interval',times:[],interval:1,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1},research:null,publicSource:'v2ex-outsourcing-authors-v1'}},
  target:{platform:'PUBLIC_WEB',access_mode:'PUBLIC_ANONYMOUS',connection_id:null,connection_version:null},
  lease:{...lease(now),...(round===undefined?{}:{public_sampling:progress(round)})},allowMonitor:true,maxRecords:budget,signal:new AbortController().signal};}
const topic=(n:number)=>({id:n,title:'AI 项目需求',content:'需要 AI 开发团队',created:epoch/1000-600,member:{id:9},
  url:`https://www.v2ex.com/t/${n}`,node:{name:'outsourcing'},replies:1});
const response=(value:unknown)=>new Response(JSON.stringify(value),{headers:{'content-type':'application/json'}});
function fixture(length=7){let now=epoch,round=0;const topics=Array.from({length},(_,n)=>topic(n+1));
  const fetcher=vi.fn(async(url:any)=>{const address=new URL(String(url));const n=Number(address.searchParams.get('topic_id'));
    return response(n?[{id:100+n,topic_id:n,member:{id:9},created:now/1000-1,content:`作者本轮补充 ${round}`}]:topics);});
  const reader=createPublicCommunityDriver({fetch:fetcher,now:()=>now});
  return {topics,fetcher,async run(next:number|undefined,budget=3){round=next??0;const run=reader.start(input(next,budget,now));
    try{return await run.completed as any[];}finally{await run.stop();now+=60000;}}};}

it('opts in on CLAIM only and leaves legacy canonical requests unchanged',()=>{
  const old=executionOperationSchema.parse(claim());expect(old).not.toHaveProperty('public_sampling_version');
  expect(executionOperationSchema.parse({...claim(),public_sampling_version:1})).toHaveProperty('public_sampling_version',1);
  expect(executionOperationSchema.parse({...claim(),public_sampling_version:undefined})).toEqual(old);
  for(const value of [null,true,0,2])expect(executionOperationSchema.safeParse({...claim(),public_sampling_version:value}).success).toBe(false);
  expect(executionOperationSchema.safeParse({...claim(),operation:'RENEW',lease_id:id(7),execution_generation:1,public_sampling_version:1}).success).toBe(false);
});
it('negotiates via an explicit read-only support query without changing the legacy route',()=>{
  expect(validatedExecutionOperation({operation:'execution.support'})).toMatchObject({path:'/api/ui/execution-support',method:'GET'});
  expect(validatedExecutionOperation({operation:'execution.support',samplingVersion:1})).toMatchObject({path:'/api/ui/execution-support?sampling_version=1',method:'GET'});
  expect(validatedExecutionOperation({operation:'execution.support',samplingVersion:2})).toBeNull();
});
it('accepts the negotiated frozen round only when the CLAIM requested it',()=>{
  const request=executionOperationSchema.parse({...claim(),public_sampling_version:1});
  const receipt={...lease(),public_sampling:progress(2)};
  expect(parseExecutionReceipt(receipt,request)).toEqual(receipt);
  expect(()=>parseExecutionReceipt(lease(),request)).toThrow('EXECUTION_RECEIPT_INVALID');
  expect(()=>parseExecutionReceipt(receipt,executionOperationSchema.parse(claim()))).toThrow('EXECUTION_RECEIPT_INVALID');
  expect(parseExecutionReceipt(lease(),executionOperationSchema.parse(claim()))).toEqual(lease());
  for(const extra of [{round:-1},{round:2147483648},{round:1.5},{round:true},{plan_id:'other'},{source_id:'other'},{cursor:'injected'}])
    expect(executionReceiptSchema.safeParse({...receipt,public_sampling:{...progress(),...extra}}).success).toBe(false);
  expect(executionReceiptSchema.safeParse({...receipt,operation:'RENEW'}).success).toBe(false);
});
it('keeps the latest topic and rotates the tail, rereading author changes inside the original request budget',async()=>{
  const f=fixture(),results=[];
  for(let round=0;round<4;round++){
    const records=await f.run(round);results.push(records.map(r=>r.external_source_id));
    expect(records[0].source_context.author_replies[0].body).toBe(`作者本轮补充 ${round}`);
    expect(records[0].body).toBe('需要 AI 开发团队');
  }
  expect(results).toEqual([['1','2','3'],['1','4','5'],['1','6','7'],['1','2','3']]);
  expect(f.fetcher).toHaveBeenCalledTimes(16);
});
it('alternates latest and older entries with a one-topic budget',async()=>{
  const f=fixture(),results=[];for(let round=0;round<6;round++)results.push((await f.run(round,1))[0].external_source_id);
  expect(results).toEqual(['1','2','1','3','1','4']);expect(f.fetcher).toHaveBeenCalledTimes(12);
});
it.each([0,1,2])('handles %i available entries without duplicates or extra requests',async count=>{
  const f=fixture(count),records=await f.run(2147483647);
  expect(records.map(r=>r.external_source_id)).toEqual(Array.from({length:count},(_,n)=>String(n+1)));
  expect(f.fetcher).toHaveBeenCalledTimes(1+count);
});
it('keeps legacy first-page sampling and never refills excluded rotated entries',async()=>{
  const f=fixture();expect((await f.run(undefined)).map(r=>r.external_source_id)).toEqual(['1','2','3']);
  f.topics[0].content='招聘 AI';f.topics[3].content='非匹配内容';f.topics[3].title='无关';f.topics[4].content='招聘 AI';
  expect(await f.run(1)).toEqual([]);expect(f.fetcher).toHaveBeenCalledTimes(5);
});
it.each(['once','source','renew','unapproved'])('rejects sampling outside its %s authority before any read',async kind=>{
  const value=input(1);if(kind==='once'){value.snapshot.configuration.mode='once';value.snapshot.configuration.schedule=null;}
  if(kind==='source')value.lease.public_sampling.source_id='v2ex-latest-v1';
  if(kind==='renew')value.lease.operation='RENEW';if(kind==='unapproved')delete value.allowMonitor;
  const fetcher=vi.fn();const run=createPublicCommunityDriver({fetch:fetcher,now:()=>epoch}).start(value);
  await expect(run.completed).rejects.toThrow('PUBLIC_SOURCE_INVALID_INPUT');await run.stop();expect(fetcher).not.toHaveBeenCalled();
});
