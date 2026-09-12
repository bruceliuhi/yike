import {expect,it,vi} from 'vitest';
import {executionReceiptSchema,parseExecutionReceipt} from '../src/shared/executionReceipt';
import {executionOperationSchema} from '../src/shared/executionOperation';
import {createPublicCommunityDriver} from '../src/main/publicCommunityDriver';
import {candidateSubmissionSchema} from '../src/shared/candidateSubmission';
import {parseCandidateReceipt} from '../src/shared/candidateReceipt';
import {validatedExecutionOperation} from '../src/main/executionServicePolicy';

const now=Date.parse('2026-09-12T10:00:00Z');
const id=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const source='v2ex-outsourcing-authors-v1';
const sampling=()=>({schema_version:'public-sampling-round-v2',plan_id:id(8),source_id:source,round:1,revisit:{topic_id:'101',query:'AI'}});
const input=()=>({snapshot:{profile_version_id:id(1),strategy_version_id:id(2),platforms:['PUBLIC_WEB'],max_records:3,max_runtime_seconds:60,
 configuration:{schema_version:'research-strategy-v1',name:'项目监控',source:'search',keywords:['AI'],exclusions:['招聘'],links:[],mode:'monitor',
 schedule:{kind:'interval',times:[],interval:1,start:'00:00',end:'23:59',timezone:'UTC',policyVersion:1},research:null,publicSource:source}},
 target:{platform:'PUBLIC_WEB',access_mode:'PUBLIC_ANONYMOUS',connection_id:null,connection_version:null},
 lease:{schema_version:'execution-runtime-v1',operation:'CLAIM',request_id:id(3),task_id:id(4),run_id:id(5),platform_run_id:id(6),status:'RUNNING',stop_confirmed:false,
 lease_id:id(7),execution_generation:1,lease_expires_at:new Date(now+60000).toISOString(),deadline_at:new Date(now+60000).toISOString(),public_sampling:sampling()},
 maxRecords:3,signal:new AbortController().signal,allowMonitor:true} as any);
const topic=(n:number,content='AI项目求助')=>({id:n,title:'企业项目',content,created:now/1000-600,deleted:0,member:{id:9},node:{name:'outsourcing'},replies:1,url:`https://www.v2ex.com/t/${n}`});
const response=(v:unknown)=>new Response(JSON.stringify(v),{headers:{'content-type':'application/json'}});
const result=(outcome='READ')=>({schema_version:'public-source-revisit-v1',claim_request_id:id(3),topic_id:'101',outcome});
function fetcher(index=[topic(201),topic(202),topic(203)],old:unknown=[topic(101,'已经找到团队了')]){
 return vi.fn(async(url:any)=>String(url).includes('node_name=')?response(index):String(url).includes('topics/show')?response(old):
 response([{id:500+Number(new URL(String(url)).searchParams.get('topic_id')),topic_id:Number(new URL(String(url)).searchParams.get('topic_id')),
 member:{id:9},created:now/1000-60,content:'已经签约，请勿再联系'}]));
}
async function read(value=input(),fetch=fetcher()){
 const run=createPublicCommunityDriver({fetch,now:()=>now}).start(value);
 try{return {output:await run.completed,fetch};}finally{await run.stop();}
}
it('negotiates v2 with the existing private support operation',()=>{
 expect(validatedExecutionOperation({operation:'execution.support',samplingVersion:2})).toMatchObject({path:'/api/ui/execution-support?sampling_version=2'});
});
it('accepts only the exact negotiated v2 CLAIM response',()=>{
 const value=input();const req=executionOperationSchema.parse({schema_version:'execution-runtime-v1',request_id:id(3),operation:'CLAIM',device_id:id(10),credential_version:1,task_id:id(4),platform_run_id:id(6),public_sampling_version:2});
 expect(parseExecutionReceipt(value.lease,req)).toEqual(value.lease);
 const old={...value.lease,public_sampling:{schema_version:'public-sampling-round-v1',plan_id:id(8),source_id:source,round:1}};
 expect(()=>parseExecutionReceipt(old,req)).toThrow();
 expect(()=>parseExecutionReceipt(value.lease,{...req,public_sampling_version:1})).toThrow();
});
it.each(['0','01','101\n','9007199254740992','https://evil.invalid'])('rejects unsafe revisit topic %j',topic_id=>{
 const value=input();value.lease.public_sampling.revisit.topic_id=topic_id;
 expect(executionReceiptSchema.safeParse(value.lease).success).toBe(false);
});
it('revisits off-index evidence and author changes even after original keywords disappear',async()=>{
 const {output,fetch}=await read();expect(output).toMatchObject({publicRevisit:result(),records:[{external_source_id:'201'},{external_source_id:'203'},
 {external_source_id:'101',body:'已经找到团队了',query:'AI',source_context:{author_replies:[{body:'已经签约，请勿再联系'}]}}]});
 expect(fetch).toHaveBeenCalledTimes(5);
 for(const call of fetch.mock.calls)expect(String(call[0])).toMatch(/^https:\/\/www.v2ex.com\/api\//);
});
it('deduplicates the index against the reserved revisit slot before sampling',async()=>{
 const {output,fetch}=await read(input(),fetcher([topic(101),topic(201),topic(202)]));
 expect((output as any).records.map((r:any)=>r.external_source_id)).toEqual(['201','202','101']);expect(fetch).toHaveBeenCalledTimes(5);
});
it('with one record of budget reads only the reserved old topic, not extra new replies',async()=>{
 const value=input();value.maxRecords=1;const {output,fetch}=await read(value);
 expect((output as any).records.map((r:any)=>r.external_source_id)).toEqual(['101']);expect(fetch).toHaveBeenCalledTimes(3);
});
it.each([[],[{...topic(101),deleted:1}],[topic(101,' ')]].map(old=>({old})))('records unavailable without claiming deletion for a successful empty/hidden response',async({old})=>{
 const value=input();value.maxRecords=1;const {output}=await read(value,fetcher([],old));
 expect(output).toEqual({records:[],publicRevisit:result('UNAVAILABLE')});
});
it.each([403,404,429,500])('HTTP %s does not become a committed unavailable result',async status=>{
 const base=fetcher();const fetch=vi.fn(async(url:any)=>String(url).includes('topics/show.json?id=')?new Response('{}',{status}):base(url));
 await expect(read(input(),fetch)).rejects.toThrow('PUBLIC_SOURCE_FAILED');
});
it.each([[topic(999)],[{...topic(101),node:{name:'qna'}}],[{...topic(101),url:'https://attacker.invalid/t/101'}],
 [{...topic(101),deleted:1,url:'https://attacker.invalid/t/101'}],[topic(101),topic(101)]].map(old=>({old})))('rejects unrelated or ambiguous old-source responses',async({old})=>{
 await expect(read(input(),fetcher([],old))).rejects.toThrow('PUBLIC_SOURCE_FAILED');
});
it.each(['query','even','source','once'])('rejects invalid revisit authority before network: %s',async kind=>{
 const value=input();if(kind==='query')value.lease.public_sampling.revisit.query='not confirmed';
 if(kind==='even')value.lease.public_sampling.round=2;
 if(kind==='source')value.lease.public_sampling.source_id='v2ex-latest-v1';
 if(kind==='once'){value.snapshot.configuration.mode='once';value.snapshot.configuration.schedule=null;}
 const fetch=fetcher();await expect(read(value,fetch)).rejects.toThrow('PUBLIC_SOURCE_INVALID_INPUT');expect(fetch).not.toHaveBeenCalled();
});
it('v2 with no selected old source keeps the legacy array path and fresh discovery',async()=>{
 const value=input();value.lease.public_sampling.revisit=null;value.lease.public_sampling.round=2;
 const {output}=await read(value);expect(Array.isArray(output)).toBe(true);expect(output).toHaveLength(3);
});
it('batch receipt must exactly echo the signed unavailable result even with no records',()=>{
 const value=input();const batch=candidateSubmissionSchema.parse({schema_version:'candidate-upload-v1',request_id:id(20),platform:'PUBLIC_WEB',profile_version_id:id(1),strategy_version_id:id(2),
 execution:{device_id:id(10),credential_version:1,task_id:id(4),run_id:id(5),platform_run_id:id(6),lease_id:id(7),execution_generation:1,access_mode:'PUBLIC_ANONYMOUS',connection_id:null,connection_version:null},records:[],public_revisit:result('UNAVAILABLE')});
 const receipt={schema_version:'candidate-receipt-v1',request_id:id(20),task_id:id(4),run_id:id(5),platform_run_id:id(6),accepted_count:0,received_at:'2026-09-12T10:00:00Z',items:[],public_revisit:result('UNAVAILABLE')};
 expect(parseCandidateReceipt(receipt,batch).public_revisit).toEqual(batch.public_revisit);
 expect(()=>parseCandidateReceipt({...receipt,public_revisit:undefined},batch)).toThrow();
 expect(()=>parseCandidateReceipt({...receipt,public_revisit:result('READ')},batch)).toThrow();
 expect(()=>candidateSubmissionSchema.parse({...batch,public_revisit:result('READ')})).toThrow();
 expect(value.lease.public_sampling.revisit.topic_id).toBe(batch.public_revisit?.topic_id);
});
