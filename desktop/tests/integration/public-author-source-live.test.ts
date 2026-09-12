import {expect,it} from 'vitest';
import {randomUUID} from 'node:crypto';
import {createPublicCommunityDriver} from '../../src/main/publicCommunityDriver';
import {candidateSubmissionSchema} from '../../src/shared/candidateSubmission';

it.skipIf(process.env.YIKE_PUBLIC_AUTHOR_LIVE!=='1')('reads actual fixed project source and bounded author context without retry or external messages',async()=>{
 const now=Date.now(),id=()=>randomUUID();let requests=0;
 const reader=createPublicCommunityDriver({fetch:async(url,init)=>{requests++;return fetch(url,init);}});
 const run=reader.start({snapshot:{profile_version_id:id(),strategy_version_id:id(),platforms:['PUBLIC_WEB'],max_records:3,max_runtime_seconds:30,
 configuration:{schema_version:'research-strategy-v1',name:'公开项目补证实测',source:'search',keywords:['AI','找','开发','需求','接','系统'],exclusions:[],links:[],mode:'once',schedule:null,research:null,publicSource:'v2ex-outsourcing-authors-v1'}},
 target:{platform:'PUBLIC_WEB',access_mode:'PUBLIC_ANONYMOUS',connection_id:null,connection_version:null},
 lease:{schema_version:'execution-runtime-v1',operation:'CLAIM',request_id:id(),task_id:id(),run_id:id(),platform_run_id:id(),status:'RUNNING',stop_confirmed:false,
 lease_id:id(),execution_generation:1,lease_expires_at:new Date(now+30000).toISOString(),deadline_at:new Date(now+30000).toISOString()},
 maxRecords:3,signal:new AbortController().signal} as any);
 try{const records=candidateSubmissionSchema.shape.records.parse(await run.completed);
  expect(requests).toBe(1+records.length);expect(requests).toBeLessThanOrEqual(4);
  for(const record of records){expect(record.source_context).toBeDefined();expect(record.source_context?.supplements_read).toBe(false);}
  console.info(JSON.stringify({kind:'REAL_PUBLIC_SOURCE_SAMPLE_NOT_QUALIFIED_LEADS',requests,records:records.map(r=>({id:r.external_source_id,reply_count:r.source_context?.replies_expected,read:r.source_context?.replies_read,author_replies:r.source_context?.author_replies.length,matched:r.source_context?.replies_complete}))}));
 }finally{await run.stop();}
},30000);
