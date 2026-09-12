import {expect,it,vi} from 'vitest';
import {createHash} from 'node:crypto';
import {createForegroundCollectionController} from '../src/main/foregroundCollectionController';
import {createCollectionWorker} from '../src/main/collectionWorker';
import {createPublicCommunityDriver} from '../src/main/publicCommunityDriver';
import {newTaskDraft} from '../src/renderer/domain/models';
import {strategyPrepareRequest} from '../src/renderer/domain/researchStrategies';
const id=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
function canonical(v:any):string{return Array.isArray(v)?'['+v.map(canonical).join(',')+']':v&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}':JSON.stringify(v);}
function batch(platform:string,platformRunId:string,requestId:string,connectionId:string){return {schema_version:'candidate-upload-v1',request_id:requestId,platform,
 profile_version_id:id(3),strategy_version_id:id(4),execution:{device_id:id(2),credential_version:1,task_id:id(6),run_id:id(7),platform_run_id:platformRunId,
 lease_id:id(Number(platformRunId.slice(-2))+20),execution_generation:1,access_mode:'PLATFORM_ACCOUNT',connection_id:connectionId,connection_version:2},records:[]};}
function fixture(){
 let current=true;const requests:any[]=[];let resolveRun!:(value:any)=>void;
 const snapshot={profile_version_id:id(3),strategy_version_id:id(4),configuration:{schema_version:'research-strategy-v1',name:'原文',source:'search',keywords:['设计'],exclusions:[],links:[],mode:'once',schedule:null,research:null},platforms:['XIAOHONGSHU'],max_records:50,max_runtime_seconds:600};
 const hash=createHash('sha256').update(canonical(snapshot)).digest('hex');
 const strategy={schema_version:'strategy-confirmation-v1',strategy_version_id:id(4),profile_version_id:id(3),draft_id:id(10),draft_revision:1,profile_sha256:'b'.repeat(64),configuration_sha256:hash,snapshot,state:'CONFIRMED',created_at:'2026-09-10T00:00:00Z',confirmed_at:'2026-09-10T00:00:00Z',revoked_at:null,is_current:true,profile_current:true};
 const command={action:'START',humanConfirmed:true,requestId:id(1),profileVersionId:id(3),strategyVersionId:id(4),configurationSha256:hash,targets:[{platform:'XIAOHONGSHU',access_mode:'PLATFORM_ACCOUNT',connection_id:id(5),connection_version:2}]};
 const startReceipt={schema_version:'execution-runtime-v1',operation:'START',request_id:id(1),task_id:id(6),run_id:id(7),status:'PENDING',stop_confirmed:false,platform_runs:[{platform_run_id:id(8),platform:'XIAOHONGSHU',status:'PENDING'}]};
 const row={connection_id:id(5),device_id:id(2),platform:'XIAOHONGSHU',account_public_id:'66c01234abcdef0123456789',connection_version:2,status:'CONNECTED',connected_at:'2026-09-10T00:00:00Z',disconnected_at:null};
 const scope={device:{deviceId:id(2),credentialVersion:1},session:{userId:'owner',sessionId:id(20),isCurrent:()=>current},transport:{requestExecution:vi.fn(async(input:any)=>({ok:true,status:200,data:input.operation==='execution.support'?{schema_version:'foreground-collection-support-v1',mode:'xhs-foreground-v1'}:{task_id:id(6),run_id:id(7),status:'PENDING',stop_confirmed:false,profile_version_id:id(3),strategy_version_id:id(4),max_records:50,records_used:0,deadline_at:'2099-09-10T00:10:00Z',platform_runs:[{platform_run_id:id(8),platform:'XIAOHONGSHU',status:'PENDING',execution_generation:0,records_used:0}]}})),requestConnection:vi.fn(async()=>({ok:true,status:200,data:{items:[row]}})),requestCandidate:vi.fn()},close:vi.fn()};
 const identity={openWorkerScope:vi.fn(async()=>({ok:true,scope})),getStatus:()=>({state:'READY',...scope.device}),requestApi:vi.fn(async()=>({ok:true,status:200,data:strategy}))};
 const executionJournal={list:vi.fn(async()=>requests),read:vi.fn(async(_s:any,key:string)=>requests.find(r=>r.request_id===key)??null)};
 const candidatesJournal={list:vi.fn(async()=>[]),read:vi.fn()};
 const execution={submit:vi.fn(async(_s:any,r:any)=>{requests.push(r);return {state:'RECORDED',receipt:startReceipt};}),recover:vi.fn()};
 const worker={run:vi.fn((_input:any)=>new Promise(r=>resolveRun=r)),cancel:vi.fn()};
 const driverFactory=vi.fn(()=>({start:vi.fn()}));const resolveAccount=vi.fn(async()=>({profileId:id(30),accountPublicId:row.account_public_id}));const probe=vi.fn(async()=>true);
 const candidateRecover=vi.fn();const options:any={serviceOrigin:'https://pilot.example',identity,store:{read:vi.fn(async()=>({state:'RESOLVED',verification:{connection_id:id(5)}}))},executionJournal,candidateJournal:candidatesJournal,
  configuration:{pythonExecutable:'C:/python.exe',projectRoot:'C:/product',runtimePath:'C:/runtime',profileRoot:'C:/profiles',outputRoot:'C:/output'},
  sessions:()=>({execution,candidates:{recover:candidateRecover}}),workerFactory:()=>worker,driverFactory,resolveAccount,probe};
 return {controller:createForegroundCollectionController(options),options,identity,scope,requests,strategy,command,startReceipt,execution,executionJournal,candidatesJournal,candidateRecover,worker,driverFactory,resolveAccount,probe,finish:(value:any={state:'COMPLETED',taskCompleted:true})=>resolveRun(value),invalidate:()=>current=false};
}
function publicFixture(mixed=false){
 const f=fixture(),nativeConfiguration=f.options.configuration;
 f.options.configuration=null;
 const publicTarget={platform:'PUBLIC_WEB',access_mode:'PUBLIC_ANONYMOUS',connection_id:null,connection_version:null};
 f.command.targets=(mixed?[f.command.targets[0],publicTarget]:[publicTarget]) as any;
 f.strategy.snapshot.platforms=f.command.targets.map(t=>t.platform);
 (f.strategy.snapshot.configuration as any).publicSource='v2ex-latest-v1';
 const hash=createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');
 f.strategy.configuration_sha256=hash;f.command.configurationSha256=hash;
 f.startReceipt.platform_runs=f.command.targets.map((t,i)=>({platform_run_id:id(8+i),platform:t.platform,status:'PENDING'}));
 const read=f.scope.transport.requestExecution.getMockImplementation()!;
 f.scope.transport.requestExecution.mockImplementation(async input=>{
  const response=await read(input);
  if(input.operation==='execution.support')return {...response,data:{schema_version:'foreground-collection-support-v1',mode:'four-platform-foreground-v1',public_source:'v2ex-latest-v1'}} as any;
  return {...response,data:{...response.data,platform_runs:f.startReceipt.platform_runs.map(r=>({...r,execution_generation:0,records_used:0}))}} as any;
 });
 const publicDriverFactory=vi.fn(()=>({start:vi.fn()}));f.options.publicDriverFactory=publicDriverFactory;
 return {...f,nativeConfiguration,publicDriverFactory,controller:createForegroundCollectionController(f.options)};
}
it.each([false,true])('native Bilibili monitor negotiates progress=%s and dispatches CLAIM through real worker',async enabled=>{
 const f=fixture();f.command.targets[0].platform='BILIBILI';f.startReceipt.platform_runs[0].platform='BILIBILI';f.strategy.snapshot.platforms=['BILIBILI'];
 Object.assign(f.strategy.snapshot.configuration,{mode:'monitor',schedule:{kind:'interval',times:[],interval:1,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1}});
 f.strategy.configuration_sha256=createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');
 f.resolveAccount.mockResolvedValue({profileId:id(30),accountPublicId:'123'});
 f.scope.transport.requestExecution.mockImplementation(async(input:any)=>({ok:true,status:200,data:input.operation==='monitor.support'
  ?{schema_version:'monitor-runtime-support-v1',mode:'four-platform-monitor-v1'}
  :{schema_version:'foreground-collection-support-v1',mode:'four-platform-foreground-v1',...(input.progressVersion===1&&enabled?{native_progress:['BILIBILI']}:{})}} as any));
 const cursor={page:1,consumed_ids:[],refresh_next:false};
 f.execution.submit.mockImplementation(async(_s:any,r:any)=>{f.requests.push(r);if(r.operation==='START')return {state:'RECORDED',receipt:f.startReceipt};
  const common={schema_version:'execution-runtime-v1',request_id:r.request_id,operation:r.operation,task_id:id(6),run_id:id(7),platform_run_id:id(8),lease_id:id(90),execution_generation:1};
  return {state:'RECORDED',receipt:r.operation==='FINISH'?{...common,status:'SUCCEEDED',stop_confirmed:true,upload_request_id:r.upload_request_id,records_used:0}
   :{...common,status:'RUNNING',stop_confirmed:false,lease_expires_at:new Date(Date.now()+120000).toISOString(),deadline_at:new Date(Date.now()+600000).toISOString(),
    ...(r.native_progress_version===1?{native_progress:{schema_version:'native-search-progress-v1',adapter_version:'bili-search-items-v1',plan_id:id(99),queries:[{query:'设计',revision:0,base_batch_request_id:null,cursor}]}}:{})}} as any;});
 const candidates={submit:vi.fn(async()=>({state:'RECORDED'}))};let done:Promise<unknown>|undefined;
 const driver={start:vi.fn((input:any)=>({stop:async()=>{},completed:Promise.resolve(enabled?{records:[],nativeProgress:{schema_version:'native-search-progress-v1',adapter_version:'bili-search-items-v1',claim_request_id:input.lease.request_id,
   queries:[{query:'设计',revision:0,base_batch_request_id:null,before:cursor,after:{...cursor,refresh_next:true},page_ids:[],processed_ids:[],has_more:false,comments_scope:'BOUNDED_SAMPLE'}]}}:[])}))};
 const controller=createForegroundCollectionController({...f.options,driverFactory:()=>driver,sessions:()=>({execution:f.execution,candidates}),workerFactory:(options:any)=>{const worker=createCollectionWorker(options);return {...worker,run:(input:any)=>done=worker.run(input)};}});
 expect(await controller.startMonitor({schema_version:'execution-runtime-v1',operation:'START',request_id:id(1),device_id:id(2),credential_version:1,profile_version_id:id(3),strategy_version_id:id(4),configuration_sha256:f.strategy.configuration_sha256,targets:f.command.targets})).toMatchObject({state:'RECORDED'});
 expect(await done).toMatchObject({state:'COMPLETED'});
 expect(f.scope.transport.requestExecution).toHaveBeenCalledWith({operation:'execution.support',progressVersion:1});
 expect(f.requests.find(r=>r.operation==='CLAIM').native_progress_version).toBe(enabled?1:undefined);
 expect((candidates.submit.mock.calls[0] as any)[1].native_progress!==undefined).toBe(enabled);
 await controller.shutdown();
});
it.each((['v2ex-qna-v1','v2ex-outsourcing-authors-v1'] as const).flatMap(source=>(['once','monitor'] as const).map(mode=>({source,mode}))))('$source $mode requires a live catalog and preserves its selected source on dispatch',async({source,mode})=>{
 const f=publicFixture(),c:any=f.strategy.snapshot.configuration;
 c.publicSource=source;c.mode=mode;
 if(mode==='monitor')c.schedule={kind:'interval',times:[],interval:1,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1};
 const hash=createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');f.strategy.configuration_sha256=hash;f.command.configurationSha256=hash;
 const sourceIds=source==='v2ex-outsourcing-authors-v1'?['v2ex-latest-v1','v2ex-qna-v1',source]:['v2ex-latest-v1',source];
 const read=f.scope.transport.requestExecution.getMockImplementation()!;let expanded=false;
 f.scope.transport.requestExecution.mockImplementation(async input=>{
  if(input.operation==='monitor.support')return {ok:true,status:200,data:{schema_version:'monitor-runtime-support-v1',mode:'four-platform-monitor-v1',public_source:'v2ex-latest-v1',...(expanded?{public_sources:sourceIds}:{})}} as any;
  const response=await read(input);return input.operation==='execution.support'?{...response,data:{...response.data,...(expanded?{public_sources:sourceIds,public_monitor:true}:{})}} as any:response;
 });
 const start={schema_version:'execution-runtime-v1',operation:'START',request_id:id(1),device_id:id(2),credential_version:1,profile_version_id:id(3),strategy_version_id:id(4),configuration_sha256:hash,targets:f.command.targets};
 const run=()=>mode==='once'?f.controller.start(f.command):f.controller.startMonitor(start);
 expect(await run()).toEqual({state:'SERVICE_UNAVAILABLE'});expect(f.execution.submit).not.toHaveBeenCalled();
 expanded=true;
 expect(await f.controller.execute({action:'CAPABILITIES'})).toMatchObject({publicBinding:{sourceIds}});
 if(mode==='monitor')expect(await f.controller.validateMonitorBinding(id(3),id(4),start.targets as any)).toBe(true);
 expect(await run()).toMatchObject({state:'RECORDED'});
 expect(f.worker.run.mock.calls[0][0].strategy.snapshot.configuration.publicSource).toBe(source);
 f.finish();await f.controller.shutdown();
});
it('offers explicitly supported public source without Python, accounts or registry reads',async()=>{
 const f=publicFixture();f.probe.mockResolvedValue(false);f.scope.transport.requestConnection.mockRejectedValue(new Error());
 expect(await f.controller.execute({action:'CAPABILITIES'})).toEqual({state:'AVAILABLE',bindings:[],publicBinding:{sourceId:'v2ex-latest-v1',deviceId:id(2)}});
 expect(f.probe).not.toHaveBeenCalled();expect(f.resolveAccount).not.toHaveBeenCalled();expect(f.scope.transport.requestConnection).not.toHaveBeenCalled();
});
it('advertises public monitor only from the explicit foreground support flag',async()=>{
 const f=publicFixture();const read=f.scope.transport.requestExecution.getMockImplementation()!;
 f.scope.transport.requestExecution.mockImplementation(async input=>input.operation==='execution.support'
  ?{ok:true,status:200,data:{schema_version:'foreground-collection-support-v1',mode:'four-platform-foreground-v1',public_source:'v2ex-latest-v1',public_monitor:true}}
  :read(input));
 expect(await f.controller.execute({action:'CAPABILITIES'})).toMatchObject({state:'AVAILABLE',publicBinding:{sourceId:'v2ex-latest-v1',deviceId:id(2),monitorSupported:true}});
});
it('starts public-only source with confirmed source hash and existing persisted execution, not native runtime',async()=>{
 const f=publicFixture();expect(await f.controller.start(f.command)).toMatchObject({state:'RECORDED'});
 expect(f.worker.run).toHaveBeenCalledWith(expect.objectContaining({platformRunId:id(8),platformMaxRecords:50,strategy:f.strategy}));
 expect(f.publicDriverFactory).toHaveBeenCalledTimes(1);expect(f.probe).not.toHaveBeenCalled();expect(f.resolveAccount).not.toHaveBeenCalled();expect(f.driverFactory).not.toHaveBeenCalled();
 f.finish();await f.controller.shutdown();
});
it.each(['source','support','session','claimed'])('refuses public %s mismatch before any source driver starts',async fault=>{
 const f=publicFixture();
 if(fault==='source'){
  delete (f.strategy.snapshot.configuration as any).publicSource;
  const hash=createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');
  f.strategy.configuration_sha256=hash;f.command.configurationSha256=hash;
 }
 if(fault==='support')f.scope.transport.requestExecution.mockResolvedValue({ok:true,status:200,data:{schema_version:'foreground-collection-support-v1',mode:'four-platform-foreground-v1'}} as any);
 if(fault==='session')f.invalidate();
 if(fault==='claimed')f.requests.push({operation:'CLAIM',task_id:id(6),platform_run_id:id(8),request_id:id(99)});
 expect(await f.controller.start(f.command)).not.toMatchObject({state:'RECORDED'});
 expect(f.publicDriverFactory).not.toHaveBeenCalled();expect(f.worker.run).not.toHaveBeenCalled();
});
it('late native setup preserves the same active controller and serial mixed source budget',async()=>{
 const f=publicFixture(true);
 expect(await f.controller.start(f.command)).toMatchObject({state:'SERVICE_UNAVAILABLE'});
 f.controller.configureNativeRuntime(f.nativeConfiguration);
 expect(await f.controller.start(f.command)).toMatchObject({state:'RECORDED'});
 expect(f.worker.run.mock.calls[0][0]).toMatchObject({platformRunId:id(8),platformMaxRecords:25});
 f.controller.configureNativeRuntime(f.nativeConfiguration);
 expect(f.controller.canStart()).toBe(false);
 f.finish({state:'COMPLETED',taskCompleted:false});await new Promise(r=>setImmediate(r));
 expect(f.worker.run.mock.calls[1][0]).toMatchObject({platformRunId:id(9),platformMaxRecords:25});
 expect(f.resolveAccount).toHaveBeenCalledTimes(1);expect(f.publicDriverFactory).toHaveBeenCalledTimes(1);
 f.finish();await f.controller.shutdown();
});
it('runs the actual controller, worker and public driver through CLAIM, evidence upload and FINISH',async()=>{
 const f=publicFixture(),events:string[]=[];let done:Promise<unknown>|undefined;
 const fetcher=vi.fn(async()=>{events.push('FETCH');return new Response(JSON.stringify([{id:12,title:'设计需求',content:'需要企业系统设计',
  created:Math.floor(Date.now()/1000)-60,url:'https://www.v2ex.com/t/12',member:{id:9}}]),{headers:{'content-type':'application/json'}});});
 const candidates={submit:vi.fn(async(_s:any,_batch:any)=>{events.push('UPLOAD');return {state:'RECORDED'};})};
 f.execution.submit.mockImplementation(async(_s:any,r:any)=>{
  events.push(r.operation);f.requests.push(r);
  if(r.operation==='START')return {state:'RECORDED',receipt:f.startReceipt} as any;
  const common={schema_version:'execution-runtime-v1',request_id:r.request_id,operation:r.operation,task_id:id(6),run_id:id(7),
   platform_run_id:id(8),lease_id:id(90),execution_generation:1};
  return {state:'RECORDED',receipt:r.operation==='FINISH'?{...common,status:'SUCCEEDED',stop_confirmed:true,upload_request_id:r.upload_request_id,records_used:1}
   :{...common,status:'RUNNING',stop_confirmed:false,lease_expires_at:new Date(Date.now()+120000).toISOString(),deadline_at:new Date(Date.now()+600000).toISOString()}} as any;
 });
 const controller=createForegroundCollectionController({...f.options,
  publicDriverFactory:()=>createPublicCommunityDriver({fetch:fetcher}),sessions:()=>({execution:f.execution,candidates}),
  workerFactory:(options:any)=>{const worker=createCollectionWorker(options);return {...worker,run:(input:any)=>done=worker.run(input)};}});
 expect(await controller.start(f.command)).toMatchObject({state:'RECORDED'});
 expect(await done).toMatchObject({state:'COMPLETED',taskCompleted:true});
 expect(events).toEqual(['START','CLAIM','FETCH','UPLOAD','FINISH']);
 expect(candidates.submit.mock.calls[0][1]).toMatchObject({platform:'PUBLIC_WEB',profile_version_id:id(3),strategy_version_id:id(4),
  execution:{access_mode:'PUBLIC_ANONYMOUS',connection_id:null,connection_version:null,device_id:id(2)},
  records:[{kind:'PAGE',body:'需要企业系统设计',public_url:'https://www.v2ex.com/t/12',collector_version:'v2ex-latest-v1'}]});
 expect(f.resolveAccount).not.toHaveBeenCalled();expect(f.probe).not.toHaveBeenCalled();await controller.shutdown();
});
it('cancelling between native and public targets prevents the delayed public launch',async()=>{
 const f=publicFixture(true);f.controller.configureNativeRuntime(f.nativeConfiguration);
 const read=f.scope.transport.requestExecution.getMockImplementation()!;let release!:()=>void,entered!:()=>void;
 const ready=new Promise<void>(resolve=>entered=resolve),hold=new Promise<void>(resolve=>release=resolve);let supportReads=0;
 f.scope.transport.requestExecution.mockImplementation(async input=>{
  if(input.operation==='execution.support'&&++supportReads===2){entered();await hold;}return read(input);
 });
 expect(await f.controller.start(f.command)).toMatchObject({state:'RECORDED'});f.finish({state:'COMPLETED',taskCompleted:false});
 await ready;f.controller.cancel(id(6));release();await f.controller.stop(id(6));
 expect(f.publicDriverFactory).not.toHaveBeenCalled();expect(f.worker.run).toHaveBeenCalledTimes(1);await f.controller.shutdown();
});
it('accepts a new native once configuration prepared by the ordinary renderer',async()=>{
 const f=fixture(),draft={...newTaskDraft(),id:id(10),revision:1,name:'设计需求',profileId:id(3),profileVersion:1,
  platforms:['xhs' as const],accounts:{xhs:'66c01234abcdef0123456789'},terms:[{id:'term',value:'设计',origin:'manual' as const,edited:false}]};
 const prepared=strategyPrepareRequest(draft,id(1),{max_records:50,max_runtime_seconds:600});
 f.strategy.snapshot.configuration=prepared.configuration as any;
 f.strategy.configuration_sha256=f.command.configurationSha256=createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');
 expect(await f.controller.start(f.command)).toMatchObject({state:'RECORDED'});
 expect(f.worker.run).toHaveBeenCalledTimes(1);f.finish();await f.controller.shutdown();
});
it.each(['once','monitor'] as const)('starts confirmed Bilibili links only with explicit %s support',async mode=>{
 const f=fixture();f.command.targets[0]={platform:'BILIBILI',access_mode:'PLATFORM_ACCOUNT',connection_id:id(5),connection_version:2};
 f.strategy.snapshot.platforms=['BILIBILI'];f.startReceipt.platform_runs[0].platform='BILIBILI';
 const c:any=f.strategy.snapshot.configuration;c.source='links';c.keywords=[];c.links=['https://www.bilibili.com/video/BV1d54y1g7db'];c.mode=mode;
 if(mode==='monitor')c.schedule={kind:'interval',times:[],interval:1,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1};
 const hash=createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');f.strategy.configuration_sha256=hash;f.command.configurationSha256=hash;
 f.resolveAccount.mockResolvedValue({profileId:id(30),accountPublicId:'123456'});
 const support=mode==='monitor'?{schema_version:'monitor-runtime-support-v1',mode:'four-platform-public-bili-links-monitor-v1',native_links:['BILIBILI']}
  :{schema_version:'foreground-collection-support-v1',mode:'four-platform-public-bili-links-monitor-v1',native_links:['BILIBILI']};
 f.scope.transport.requestExecution.mockImplementation(async(input:any)=>input.operation.endsWith('support')?{ok:true,status:200,data:support}:{ok:true,status:200,data:{task_id:id(6),run_id:id(7),status:'PENDING',stop_confirmed:false,profile_version_id:id(3),strategy_version_id:id(4),max_records:50,records_used:0,deadline_at:'2099-09-10T00:10:00Z',platform_runs:[{platform_run_id:id(8),platform:'BILIBILI',status:'PENDING',execution_generation:0,records_used:0}]}});
 const start={schema_version:'execution-runtime-v1',operation:'START',request_id:id(1),device_id:id(2),credential_version:1,profile_version_id:id(3),strategy_version_id:id(4),configuration_sha256:hash,targets:f.command.targets};
 const result=mode==='once'?await f.controller.start(f.command):await f.controller.startMonitor(start);
 expect(result).toMatchObject({state:'RECORDED'});expect(f.driverFactory).toHaveBeenCalledWith(expect.objectContaining({allowMonitor:mode==='monitor'||undefined,binding:expect.objectContaining({platform:'BILIBILI',expectedAccountPublicId:'123456'})}));
 f.finish();await f.controller.shutdown();
});
it('does not submit the same Bilibili link snapshot without the explicit server declaration',async()=>{
 const f=fixture();f.command.targets[0]={platform:'BILIBILI',access_mode:'PLATFORM_ACCOUNT',connection_id:id(5),connection_version:2};
 f.strategy.snapshot.platforms=['BILIBILI'];const c:any=f.strategy.snapshot.configuration;c.source='links';c.keywords=[];c.links=['https://www.bilibili.com/video/BV1d54y1g7db'];
 const hash=createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');f.strategy.configuration_sha256=hash;f.command.configurationSha256=hash;
 f.scope.transport.requestExecution.mockResolvedValue({ok:true,status:200,data:{schema_version:'foreground-collection-support-v1',mode:'four-platform-foreground-v1'}} as any);
 expect(await f.controller.start(f.command)).toEqual({state:'SERVICE_UNAVAILABLE'});expect(f.execution.submit).not.toHaveBeenCalled();expect(f.driverFactory).not.toHaveBeenCalled();
});
it('advertises Bilibili link eligibility only from the exact support response and bound account',async()=>{
 const f=fixture();const bili={connection_id:id(5),device_id:id(2),platform:'BILIBILI',account_public_id:'123456',connection_version:2,status:'CONNECTED',connected_at:'2026-09-10T00:00:00Z',disconnected_at:null};
 f.scope.transport.requestConnection.mockResolvedValue({ok:true,status:200,data:{items:[bili]}} as any);
 f.scope.transport.requestExecution.mockResolvedValue({ok:true,status:200,data:{schema_version:'foreground-collection-support-v1',mode:'four-platform-public-bili-links-monitor-v1',native_links:['BILIBILI']}} as any);
 f.resolveAccount.mockResolvedValue({profileId:id(30),accountPublicId:'123456'});
 expect(await f.controller.execute({action:'CAPABILITIES'})).toMatchObject({state:'AVAILABLE',linkPlatforms:['BILIBILI'],bindings:[{platform:'BILIBILI'}]});
});
it('launches one bound background worker after fresh strategy, account, runtime and persisted START',async()=>{
 const f=fixture();(f.strategy.snapshot.configuration as any).exclusions=['招聘'];
 const hash=createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');f.strategy.configuration_sha256=hash;f.command.configurationSha256=hash;
 expect(await f.controller.start(f.command)).toMatchObject({state:'RECORDED',receipt:f.startReceipt});
 expect(f.worker.run).toHaveBeenCalledTimes(1);expect(f.worker.run.mock.calls[0][0]).toMatchObject({startReceipt:f.startReceipt,platformRunId:id(8),strategy:f.strategy});
 expect(f.driverFactory).toHaveBeenCalledWith(expect.objectContaining({profilePath:'C:\\profiles\\'+id(30),binding:expect.objectContaining({expectedAccountPublicId:'66c01234abcdef0123456789',connection_id:id(5)})}));f.finish();await f.controller.shutdown();
});
it.each(['probe','account','strategy','session'])('never creates START or browser for failed %s readiness',async fault=>{
 const f=fixture();if(fault==='probe')f.probe.mockResolvedValue(false);if(fault==='account')f.resolveAccount.mockRejectedValue(new Error());if(fault==='strategy')f.strategy.snapshot.configuration.keywords=['篡改'];if(fault==='session')f.invalidate();
 expect(await f.controller.start(f.command)).not.toMatchObject({state:'RECORDED'});expect(f.execution.submit).not.toHaveBeenCalled();expect(f.driverFactory).not.toHaveBeenCalled();
});
it('a prior CLAIM journal marker forbids restarting an already-created task',async()=>{
 const f=fixture();f.requests.push({...f.command,operation:'CLAIM',task_id:id(6),platform_run_id:id(8),request_id:id(99)});
 expect(await f.controller.start(f.command)).toMatchObject({state:'SERVICE_UNAVAILABLE'});expect(f.worker.run).not.toHaveBeenCalled();
});
it('unknown START retains original request and never opens browser',async()=>{
 const f=fixture();f.execution.submit.mockResolvedValue({state:'UNKNOWN',requestId:id(1)} as any);
 expect(await f.controller.start(f.command)).toEqual({state:'UNKNOWN',requestId:id(1)});expect(f.worker.run).not.toHaveBeenCalled();
});
it('cancel and shutdown await the active worker without starting another',async()=>{
 const f=fixture();await f.controller.start(f.command);f.controller.cancel(id(6));expect(f.worker.cancel).toHaveBeenCalledTimes(1);
 let done=false;const closing=f.controller.shutdown().then(()=>done=true);await Promise.resolve();expect(done).toBe(false);f.finish();await closing;expect(done).toBe(true);
});
it('simultaneous recover calls are serialized before opening their scopes',async()=>{
 const f=fixture();let release!:(x:any)=>void;f.identity.openWorkerScope.mockImplementation(()=>new Promise(r=>release=r));
 const first=f.controller.execute({action:'RECOVER',taskId:id(6),humanConfirmed:true});
 const second=f.controller.execute({action:'RECOVER',taskId:id(6),humanConfirmed:true});
 expect(await Promise.race([second,Promise.resolve('pending')])).toEqual({state:'BUSY'});
 release({ok:true,scope:f.scope});await first;
});
it('queues scope opening so status reads cannot compete with another foreground opening',async()=>{
 const f=fixture();let release!:()=>void,preparing=false;
 const firstOpening=new Promise<void>(resolve=>release=resolve);
 (f.identity.openWorkerScope as any).mockImplementation(async()=>{
  if(preparing)return {ok:false,state:'BUSY'};
  preparing=true;await firstOpening;preparing=false;return {ok:true,scope:f.scope};
 });
 const first=f.controller.execute({action:'STATUS',taskId:id(6)});
 const second=f.controller.execute({action:'STATUS',taskId:id(6)});
 await new Promise(resolve=>setImmediate(resolve));
 const callsBeforeRelease=f.identity.openWorkerScope.mock.calls.length;
 release();const results=await Promise.all([first,second]);
 expect(callsBeforeRelease).toBe(1);
 expect(results.every(result=>result.state==='STATUS')).toBe(true);
 await f.controller.shutdown();
});
it('a prior physical stop failure blocks another browser and is still reported at shutdown',async()=>{
 const f=fixture();await f.controller.start(f.command);f.finish({state:'FAILED',error:'SOURCE_STOP_FAILED',taskCompleted:false});
 await new Promise(resolve=>setImmediate(resolve));
 expect(await f.controller.start({...f.command,requestId:id(90)})).toEqual({state:'SERVICE_UNAVAILABLE'});
 expect(f.driverFactory).toHaveBeenCalledTimes(1);await expect(f.controller.shutdown()).rejects.toThrow('SOURCE_STOP_FAILED');
});
it('explicit resume reads original START without letting a request id supply new intent',async()=>{
 const f=fixture();
 expect(await f.controller.resumeStart(id(1))).toEqual({state:'NOT_FOUND'});
 expect(f.execution.submit).not.toHaveBeenCalled();
 f.requests.push({schema_version:'execution-runtime-v1',request_id:id(1),operation:'START',device_id:id(2),credential_version:1,
  profile_version_id:id(3),strategy_version_id:id(4),configuration_sha256:f.command.configurationSha256,targets:f.command.targets});
 expect(await f.controller.resumeStart(id(1))).toMatchObject({state:'RECORDED'});expect(f.worker.run).toHaveBeenCalledTimes(1);f.finish();await f.controller.shutdown();
});
it.each(['start','resume'] as const)('refuses %s when server generation is already one even if local CLAIM is missing',async entry=>{
 const f=fixture();
 (f.scope.transport.requestExecution as any).mockImplementation(async(input:any)=>({ok:true,status:200,data:input.operation==='execution.support'
  ?{schema_version:'foreground-collection-support-v1',mode:'xhs-foreground-v1'}:{task_id:id(6),run_id:id(7),status:'RUNNING',stop_confirmed:false,profile_version_id:id(3),strategy_version_id:id(4),max_records:50,records_used:0,deadline_at:'2099-09-10T00:10:00Z',platform_runs:[{platform_run_id:id(8),platform:'XIAOHONGSHU',status:'RUNNING',execution_generation:1,records_used:0}]}}));
 if(entry==='resume')f.requests.push({schema_version:'execution-runtime-v1',request_id:id(1),operation:'START',device_id:id(2),credential_version:1,
  profile_version_id:id(3),strategy_version_id:id(4),configuration_sha256:f.command.configurationSha256,targets:f.command.targets});
 const result=entry==='start'?await f.controller.start(f.command):await f.controller.resumeStart(id(1));
 expect(result).toMatchObject({state:'SERVICE_UNAVAILABLE'});expect(f.worker.run).not.toHaveBeenCalled();
});
it('resumes only the pending suffix using original order when task rows are sorted and prefix FINISH is task-RUNNING',async()=>{
 const f=fixture();const targets=[f.command.targets[0],{platform:'DOUYIN',access_mode:'PLATFORM_ACCOUNT',connection_id:id(51),connection_version:2}];
 f.command.targets=targets as any;f.strategy.snapshot.platforms=['XIAOHONGSHU','DOUYIN'];
 const hash=createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');f.command.configurationSha256=hash;f.strategy.configuration_sha256=hash;
 f.startReceipt.platform_runs=[{platform_run_id:id(8),platform:'XIAOHONGSHU',status:'PENDING'},{platform_run_id:id(9),platform:'DOUYIN',status:'PENDING'}];
 const original={schema_version:'execution-runtime-v1',request_id:id(1),operation:'START',device_id:id(2),credential_version:1,profile_version_id:id(3),strategy_version_id:id(4),configuration_sha256:hash,targets};
 const claim={schema_version:'execution-runtime-v1',request_id:id(91),operation:'CLAIM',device_id:id(2),credential_version:1,task_id:id(6),platform_run_id:id(8)};
 const finish={schema_version:'execution-runtime-v1',request_id:id(92),operation:'FINISH',device_id:id(2),credential_version:1,task_id:id(6),platform_run_id:id(8),lease_id:id(90),execution_generation:1,upload_request_id:id(70)};
 f.requests.push(original,claim,finish);(f.candidatesJournal.list as any).mockResolvedValue(['batch']);
 (f.candidatesJournal.read as any).mockResolvedValue({schema_version:'candidate-upload-v1',request_id:id(70),platform:'XIAOHONGSHU',profile_version_id:id(3),strategy_version_id:id(4),
  execution:{device_id:id(2),credential_version:1,task_id:id(6),run_id:id(7),platform_run_id:id(8),lease_id:id(90),execution_generation:1,access_mode:'PLATFORM_ACCOUNT',connection_id:id(5),connection_version:2},records:[]});
 (f.scope.transport.requestExecution as any).mockImplementation(async(input:any)=>({ok:true,status:200,data:input.operation==='execution.support'
  ?{schema_version:'foreground-collection-support-v1',mode:'three-platform-foreground-v1'}:{task_id:id(6),run_id:id(7),status:'RUNNING',stop_confirmed:false,profile_version_id:id(3),strategy_version_id:id(4),max_records:50,records_used:0,deadline_at:'2099-09-10T00:10:00Z',platform_runs:[
   {platform_run_id:id(9),platform:'DOUYIN',status:'PENDING',execution_generation:0,records_used:0},{platform_run_id:id(8),platform:'XIAOHONGSHU',status:'SUCCEEDED',execution_generation:1,records_used:0}]}}));
 f.execution.recover.mockResolvedValue({state:'RECORDED',receipt:{schema_version:'execution-runtime-v1',operation:'FINISH',request_id:id(92),task_id:id(6),run_id:id(7),platform_run_id:id(8),lease_id:id(90),execution_generation:1,upload_request_id:id(70),records_used:0,status:'RUNNING',stop_confirmed:false}});
 expect(await f.controller.resumeStart(id(1))).toMatchObject({state:'RECORDED'});
 expect(f.worker.run).toHaveBeenCalledTimes(1);expect(f.worker.run.mock.calls[0][0]).toMatchObject({platformRunId:id(9),platformMaxRecords:25});
 f.finish();await f.controller.shutdown();
});
it('concurrent capability reads share one probe and bind only the protected current profile',async()=>{
 const f=fixture();const results=await Promise.all([f.controller.execute({action:'CAPABILITIES'}),f.controller.execute({action:'CAPABILITIES'})]);
 expect(results[0]).toEqual(results[1]);expect(results[0]).toMatchObject({state:'AVAILABLE',bindings:[{connectionId:id(5),deviceId:id(2)}]});
 expect(f.probe).toHaveBeenCalledTimes(1);expect(f.options.store.read).toHaveBeenCalledTimes(1);
});
it.each(['DOUYIN','BILIBILI','ZHIHU'] as const)('starts selected %s target only in its explicit server mode',async platform=>{
 const f=fixture();const account=platform==='DOUYIN'?'douyin.account-1':'123456789';
 f.command.targets[0].platform=platform as any;f.strategy.snapshot.platforms=[platform] as any;
 const hash=createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');f.command.configurationSha256=hash;f.strategy.configuration_sha256=hash;
 f.scope.transport.requestExecution.mockImplementation(async(input:any)=>({ok:true,status:200,data:input.operation==='execution.support'
  ?{schema_version:'foreground-collection-support-v1',mode:platform==='ZHIHU'?'four-platform-foreground-v1':'three-platform-foreground-v1'}
  :{task_id:id(6),run_id:id(7),status:'PENDING',stop_confirmed:false,profile_version_id:id(3),strategy_version_id:id(4),max_records:50,records_used:0,deadline_at:'2099-09-10T00:10:00Z',platform_runs:[{platform_run_id:id(8),platform,status:'PENDING',execution_generation:0,records_used:0}]}}));
 f.resolveAccount.mockResolvedValue({profileId:id(30),accountPublicId:account});
 f.startReceipt.platform_runs[0].platform=platform as any;
 expect(await f.controller.start(f.command)).toMatchObject({state:'RECORDED'});
 expect(f.driverFactory).toHaveBeenCalledWith(expect.objectContaining({binding:expect.objectContaining({platform,expectedAccountPublicId:account})}));
 f.finish();await f.controller.shutdown();
});
it('does not start a video target under legacy xhs-only support',async()=>{
 const f=fixture();f.command.targets[0].platform='DOUYIN' as any;f.strategy.snapshot.platforms=['DOUYIN'] as any;
 expect(await f.controller.start(f.command)).toEqual({state:'SERVICE_UNAVAILABLE'});
 expect(f.execution.submit).not.toHaveBeenCalled();expect(f.driverFactory).not.toHaveBeenCalled();
});
it('keeps a verified sibling capability when another one platform profile read fails',async()=>{
 const f=fixture();const dy={connection_id:id(50),device_id:id(2),platform:'DOUYIN',account_public_id:'studio_2026',connection_version:3,status:'CONNECTED',connected_at:'2026-09-10T00:00:00Z',disconnected_at:null};
 f.scope.transport.requestExecution.mockImplementation(async()=>({ok:true,status:200,data:{schema_version:'foreground-collection-support-v1',mode:'three-platform-foreground-v1'}} as any));
 f.scope.transport.requestConnection.mockResolvedValue({ok:true,status:200,data:{items:[dy]}});
 f.options.store.read.mockImplementation(async({platform}:any)=>{if(platform==='XIAOHONGSHU')throw new Error('corrupt');
  if(platform==='DOUYIN')return {state:'RESOLVED',verification:{connection_id:id(50)}};return null;});
 f.resolveAccount.mockResolvedValue({profileId:id(30),accountPublicId:'studio_2026'});
 expect(await f.controller.execute({action:'CAPABILITIES'})).toEqual({state:'AVAILABLE',bindings:[{mode:'three-platform-foreground-v1',platform:'DOUYIN',connectionId:id(50),connectionVersion:3,deviceId:id(2),accountPublicId:'studio_2026'}]});
});

it('STATUS exposes explicit recovery when multiple original platform batches exist',async()=>{
 const f=fixture();(f.candidatesJournal.list as any).mockResolvedValue(['a','b']);
 (f.candidatesJournal.read as any).mockImplementation(async(_scope:any,key:string)=>({request_id:id(key==='a'?70:71),execution:{task_id:id(6)}}));
 expect(await f.controller.execute({action:'STATUS',taskId:id(6)})).toMatchObject({state:'STATUS',recordsUsed:0,recoverable:true});
});
it('prevalidates and recovers two original batches in platform order without starting a driver',async()=>{
 const f=fixture(),left=batch('XIAOHONGSHU',id(8),id(70),id(5)),right=batch('DOUYIN',id(9),id(71),id(51));
 (f.candidatesJournal.list as any).mockResolvedValue(['right','left']);(f.candidatesJournal.read as any).mockImplementation(async(_s:any,key:string)=>key==='left'?left:right);
 (f.scope.transport.requestExecution as any).mockResolvedValue({ok:true,status:200,data:{task_id:id(6),run_id:id(7),status:'RUNNING',stop_confirmed:false,
  profile_version_id:id(3),strategy_version_id:id(4),max_records:50,records_used:0,deadline_at:'2099-09-10T00:10:00Z',platform_runs:[
   {platform_run_id:id(9),platform:'DOUYIN',status:'RUNNING',execution_generation:1,records_used:0},{platform_run_id:id(8),platform:'XIAOHONGSHU',status:'RUNNING',execution_generation:1,records_used:0}]}});
 f.candidateRecover.mockResolvedValue({state:'RECORDED'});(f.execution.submit as any).mockImplementation(async(_s:any,request:any)=>({state:'RECORDED',receipt:{schema_version:'execution-runtime-v1',operation:'FINISH',request_id:request.request_id,
  task_id:id(6),run_id:id(7),platform_run_id:request.platform_run_id,lease_id:request.lease_id,execution_generation:1,upload_request_id:request.upload_request_id,records_used:0,status:'RUNNING',stop_confirmed:false}}));
 expect(await f.controller.execute({action:'RECOVER',taskId:id(6),humanConfirmed:true})).toMatchObject({state:'STATUS'});
 expect(f.candidateRecover.mock.calls.map((call:any[])=>call[1].platformRunId)).toEqual([id(9),id(8)]);expect(f.driverFactory).not.toHaveBeenCalled();
});
it('rejects conflicting batch mappings before making any recovery write',async()=>{
 const f=fixture(),left=batch('XIAOHONGSHU',id(8),id(70),id(5)),conflict=batch('XIAOHONGSHU',id(8),id(71),id(5));
 (f.candidatesJournal.list as any).mockResolvedValue(['left','conflict']);(f.candidatesJournal.read as any).mockImplementation(async(_s:any,key:string)=>key==='left'?left:conflict);
 expect(await f.controller.execute({action:'RECOVER',taskId:id(6),humanConfirmed:true})).toEqual({state:'UNAVAILABLE'});
 expect(f.candidateRecover).not.toHaveBeenCalled();expect(f.execution.submit).not.toHaveBeenCalled();
});

it('runs a confirmed three-platform once task serially with fixed shared budgets and independent profiles',async()=>{
 const f=fixture();const platforms=['XIAOHONGSHU','DOUYIN','BILIBILI'] as const;
 f.command.targets=platforms.map((platform,index)=>({platform,access_mode:'PLATFORM_ACCOUNT',connection_id:id(50+index),connection_version:2}));
 f.strategy.snapshot.platforms=[...platforms];f.strategy.snapshot.max_records=8;
 const hash=createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');f.command.configurationSha256=hash;f.strategy.configuration_sha256=hash;
 f.startReceipt.platform_runs=platforms.map((platform,index)=>({platform_run_id:id(80+index),platform,status:'PENDING'}));
 (f.scope.transport.requestExecution as any).mockImplementation(async(input:any)=>({ok:true,status:200,data:input.operation==='execution.support'
  ?{schema_version:'foreground-collection-support-v1',mode:'three-platform-foreground-v1'}:{task_id:id(6),run_id:id(7),status:'PENDING',stop_confirmed:false,
   profile_version_id:id(3),strategy_version_id:id(4),max_records:8,records_used:0,deadline_at:'2099-09-10T00:10:00Z',
   platform_runs:platforms.map((platform,index)=>({platform_run_id:id(80+index),platform,status:'PENDING',execution_generation:0,records_used:0}))}}));
 (f.resolveAccount as any).mockImplementation(async(input:any)=>({profileId:id(31+platforms.indexOf(input.target.platform)),accountPublicId:'account'}));
 f.worker.run.mockResolvedValueOnce({state:'COMPLETED',taskCompleted:false}).mockResolvedValueOnce({state:'COMPLETED',taskCompleted:false}).mockResolvedValueOnce({state:'COMPLETED',taskCompleted:true});
 expect(await f.controller.start(f.command)).toMatchObject({state:'RECORDED'});
 await new Promise(resolve=>setImmediate(resolve));await new Promise(resolve=>setImmediate(resolve));
 expect(f.worker.run.mock.calls.map((call:any[])=>[call[0].platformRunId,call[0].platformMaxRecords])).toEqual([[id(80),3],[id(81),3],[id(82),2]]);
 expect(f.driverFactory.mock.calls.map((call:any[])=>call[0].profilePath)).toEqual(['C:\\profiles\\'+id(31),'C:\\profiles\\'+id(32),'C:\\profiles\\'+id(33)]);
 await f.controller.shutdown();
});
it.each(['upload-unknown','account-change','cancel'] as const)('stops later platforms after %s',async fault=>{
 const f=fixture(),platforms=['XIAOHONGSHU','DOUYIN','BILIBILI'] as const;
 f.command.targets=platforms.map((platform,index)=>({platform,access_mode:'PLATFORM_ACCOUNT',connection_id:id(50+index),connection_version:2}));
 f.strategy.snapshot.platforms=[...platforms];f.strategy.snapshot.max_records=8;
 const hash=createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');f.command.configurationSha256=hash;f.strategy.configuration_sha256=hash;
 f.startReceipt.platform_runs=platforms.map((platform,index)=>({platform_run_id:id(80+index),platform,status:'PENDING'}));
 (f.scope.transport.requestExecution as any).mockImplementation(async(input:any)=>({ok:true,status:200,data:input.operation==='execution.support'
  ?{schema_version:'foreground-collection-support-v1',mode:'three-platform-foreground-v1'}:{task_id:id(6),run_id:id(7),status:'PENDING',stop_confirmed:false,
   profile_version_id:id(3),strategy_version_id:id(4),max_records:8,records_used:0,deadline_at:'2099-09-10T00:10:00Z',platform_runs:platforms.map((platform,index)=>({platform_run_id:id(80+index),platform,status:'PENDING',execution_generation:0,records_used:0}))}}));
 if(fault==='account-change')(f.resolveAccount as any).mockImplementation(async()=>{if(f.resolveAccount.mock.calls.length===4)throw new Error('changed');return {profileId:id(30),accountPublicId:'account'};});
 if(fault!=='cancel')f.worker.run.mockResolvedValueOnce({state:'COMPLETED',taskCompleted:false});
 if(fault==='upload-unknown')f.worker.run.mockResolvedValueOnce({state:'UPLOAD_UNKNOWN',taskCompleted:false,recoveryKey:{platformRunId:id(81),requestId:id(70)}});
 expect(await f.controller.start(f.command)).toMatchObject({state:'RECORDED'});if(fault==='cancel'){f.controller.cancel(id(6));f.finish({state:'STOPPED',reason:'CANCELLED',taskCompleted:false});}
 await new Promise(resolve=>setImmediate(resolve));await new Promise(resolve=>setImmediate(resolve));
 expect(f.worker.run).toHaveBeenCalledTimes(fault==='upload-unknown'?2:1);expect(f.worker.run.mock.calls.some((call:any[])=>call[0].platformRunId===id(82))).toBe(false);
 await f.controller.shutdown();
});

it('rejects a shared record budget smaller than the selected platform count',async()=>{
 const f=fixture();f.command.targets=[f.command.targets[0],{...f.command.targets[0],platform:'DOUYIN',connection_id:id(51)}];
 f.strategy.snapshot.platforms=['XIAOHONGSHU','DOUYIN'];f.strategy.snapshot.max_records=1;
 const hash=createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');f.command.configurationSha256=hash;f.strategy.configuration_sha256=hash;
 expect(await f.controller.start(f.command)).toEqual({state:'SERVICE_UNAVAILABLE'});expect(f.execution.submit).not.toHaveBeenCalled();
});

it('monitor source stop failure latches the same foreground slot',async()=>{
 const f=fixture();const c:any=f.strategy.snapshot.configuration;c.mode='monitor';c.exclusions=['招聘'];c.schedule={kind:'interval',times:[],interval:1,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1};
 const hash=createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');f.strategy.configuration_sha256=hash;
 (f.scope.transport.requestExecution as any).mockImplementation(async(input:any)=>input.operation==='monitor.support'?{ok:true,status:200,data:{schema_version:'monitor-runtime-support-v1',mode:'three-platform-monitor-v1'}}:{ok:false,status:400,error:'unexpected'});
 const start={schema_version:'execution-runtime-v1',operation:'START',request_id:id(1),device_id:id(2),credential_version:1,profile_version_id:id(3),strategy_version_id:id(4),configuration_sha256:hash,targets:f.command.targets};
 expect(await f.controller.startMonitor(start)).toMatchObject({state:'RECORDED'});expect(f.worker.run.mock.calls[0][0]).toMatchObject({allowMonitor:true,platformMaxRecords:50});
 f.finish({state:'FAILED',error:'SOURCE_STOP_FAILED',taskCompleted:false});await new Promise(resolve=>setImmediate(resolve));
 expect(f.controller.canStart()).toBe(false);await expect(f.controller.stop(id(6))).rejects.toThrow('SOURCE_STOP_FAILED');
 await expect(f.controller.shutdown()).rejects.toThrow('SOURCE_STOP_FAILED');
});

it('validates and starts public-only monitor without native runtime or account probing',async()=>{
 const f=publicFixture();const c:any=f.strategy.snapshot.configuration;c.mode='monitor';c.schedule={kind:'interval',times:[],interval:1,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1};
 const hash=createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');f.strategy.configuration_sha256=hash;
 const read=f.scope.transport.requestExecution.getMockImplementation()!;
 f.scope.transport.requestExecution.mockImplementation(async input=>input.operation==='monitor.support'
  ?{ok:true,status:200,data:{schema_version:'monitor-runtime-support-v1',mode:'four-platform-monitor-v1',public_source:'v2ex-latest-v1'}}:read(input));
 const start={schema_version:'execution-runtime-v1',operation:'START',request_id:id(1),device_id:id(2),credential_version:1,profile_version_id:id(3),strategy_version_id:id(4),configuration_sha256:hash,targets:f.command.targets};
 expect(await f.controller.validateMonitorBinding(id(3),id(4),start.targets as any)).toBe(true);
 expect(await f.controller.startMonitor(start)).toMatchObject({state:'RECORDED'});
 expect(f.worker.run).toHaveBeenCalledWith(expect.objectContaining({allowMonitor:true}));
 expect(f.probe).not.toHaveBeenCalled();expect(f.resolveAccount).not.toHaveBeenCalled();
 f.finish();await f.controller.shutdown();
});

it.each([false,true])('runs public monitor through real controller-worker-driver with negotiated sampling=%s',async sampling=>{
 const f=publicFixture();const c:any=f.strategy.snapshot.configuration;c.mode='monitor';c.schedule={kind:'interval',times:[],interval:1,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1};
 f.strategy.snapshot.max_records=3;
 const hash=createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');f.strategy.configuration_sha256=hash;
 const base=f.scope.transport.requestExecution.getMockImplementation()!;f.scope.transport.requestExecution.mockImplementation(async input=>input.operation==='monitor.support'
  ?{ok:true,status:200,data:{schema_version:'monitor-runtime-support-v1',mode:'four-platform-monitor-v1',public_source:'v2ex-latest-v1'}}:
   input.operation==='execution.support'&&(input as any).samplingVersion===1&&sampling
    ?{ok:true,status:200,data:{schema_version:'foreground-collection-support-v1',mode:'four-platform-foreground-v1',public_source:'v2ex-latest-v1',public_monitor:true,public_sampling:'committed-round-v1'}}:base(input));
 const fetcher=vi.fn(async()=>new Response(JSON.stringify(Array.from({length:7},(_,n)=>({id:12+n,title:'设计需求',content:'需要企业系统设计',created:Math.floor(Date.now()/1000)-60,url:`https://www.v2ex.com/t/${12+n}`,member:{id:9}}))),{headers:{'content-type':'application/json'}}));
 const candidates={submit:vi.fn(async()=>({state:'RECORDED'}))};let done:Promise<unknown>|undefined;
 f.execution.submit.mockImplementation(async(_s:any,r:any)=>{f.requests.push(r);if(r.operation==='START')return {state:'RECORDED',receipt:f.startReceipt} as any;
  const common={schema_version:'execution-runtime-v1',request_id:r.request_id,operation:r.operation,task_id:id(6),run_id:id(7),platform_run_id:id(8),lease_id:id(90),execution_generation:1};
  return {state:'RECORDED',receipt:r.operation==='FINISH'?{...common,status:'SUCCEEDED',stop_confirmed:true,upload_request_id:r.upload_request_id,records_used:3}:{...common,status:'RUNNING',stop_confirmed:false,lease_expires_at:new Date(Date.now()+120000).toISOString(),deadline_at:new Date(Date.now()+600000).toISOString(),
    ...(r.operation==='CLAIM'&&r.public_sampling_version===1?{public_sampling:{schema_version:'public-sampling-round-v1',plan_id:id(99),source_id:'v2ex-latest-v1',round:1}}:{})}} as any;});
 const controller=createForegroundCollectionController({...f.options,publicDriverFactory:()=>createPublicCommunityDriver({fetch:fetcher}),sessions:()=>({execution:f.execution,candidates}),workerFactory:(options:any)=>{const worker=createCollectionWorker(options);return {...worker,run:(input:any)=>done=worker.run(input)};}});
 const start={schema_version:'execution-runtime-v1',operation:'START',request_id:id(1),device_id:id(2),credential_version:1,profile_version_id:id(3),strategy_version_id:id(4),configuration_sha256:hash,targets:f.command.targets};
 expect(await controller.startMonitor(start)).toMatchObject({state:'RECORDED'});expect(await done).toMatchObject({state:'COMPLETED',taskCompleted:true});
 expect(f.scope.transport.requestExecution).toHaveBeenCalledWith({operation:'execution.support',samplingVersion:1});
 const claimed=f.requests.find((r:any)=>r.operation==='CLAIM');expect(claimed.public_sampling_version).toBe(sampling?1:undefined);
 expect(fetcher).toHaveBeenCalledTimes(1);
 expect((candidates.submit.mock.calls[0] as any)[1].records.map((r:any)=>r.external_source_id)).toEqual(sampling?['12','15','16']:['12','13','14']);
 await controller.shutdown();
});

it('serializes same-device native and public monitor targets through the shared slot',async()=>{
 const f=publicFixture(true);f.controller.configureNativeRuntime(f.nativeConfiguration);const c:any=f.strategy.snapshot.configuration;c.mode='monitor';c.schedule={kind:'interval',times:[],interval:1,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1};
 const hash=createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');f.strategy.configuration_sha256=hash;
 const read=f.scope.transport.requestExecution.getMockImplementation()!;f.scope.transport.requestExecution.mockImplementation(async input=>input.operation==='monitor.support'
  ?{ok:true,status:200,data:{schema_version:'monitor-runtime-support-v1',mode:'four-platform-monitor-v1',public_source:'v2ex-latest-v1'}}:
   input.operation==='execution.support'&&(input as any).samplingVersion===1
    ?{ok:true,status:200,data:{schema_version:'foreground-collection-support-v1',mode:'four-platform-foreground-v1',public_source:'v2ex-latest-v1',public_monitor:true,public_sampling:'committed-round-v1'}}:read(input));
 const start={schema_version:'execution-runtime-v1',operation:'START',request_id:id(1),device_id:id(2),credential_version:1,profile_version_id:id(3),strategy_version_id:id(4),configuration_sha256:hash,targets:f.command.targets};
 expect(await f.controller.startMonitor(start)).toMatchObject({state:'RECORDED'});expect(f.worker.run).toHaveBeenCalledTimes(1);
 f.finish({state:'COMPLETED',taskCompleted:false});await new Promise(resolve=>setImmediate(resolve));await new Promise(resolve=>setImmediate(resolve));
 expect(f.worker.run).toHaveBeenCalledTimes(2);expect(f.worker.run.mock.calls[1][0]).toMatchObject({platformRunId:id(9),allowMonitor:true,allowPublicSampling:true});
 expect(f.worker.run.mock.calls[0][0]).not.toHaveProperty('allowPublicSampling');
 expect(f.publicDriverFactory).toHaveBeenCalledTimes(1);f.finish();await f.controller.shutdown();
});

it.each(['invalid','unavailable','session'])('sampling negotiation %s stops before START without falling back or retrying',async kind=>{
 const f=publicFixture();Object.assign(f.strategy.snapshot.configuration,{mode:'monitor',schedule:{kind:'interval',times:[],interval:1,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1}});
 f.strategy.configuration_sha256=createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');
 const read=f.scope.transport.requestExecution.getMockImplementation()!;
 f.scope.transport.requestExecution.mockImplementation(async input=>{
  if(input.operation==='monitor.support')return {ok:true,status:200,data:{schema_version:'monitor-runtime-support-v1',mode:'four-platform-monitor-v1',public_source:'v2ex-latest-v1'}} as any;
  if(input.operation==='execution.support'&&(input as any).samplingVersion===1){
   if(kind==='unavailable')return {ok:false,status:503,error:'unavailable'} as any;
   if(kind==='session')f.invalidate();
   return {ok:true,status:200,data:{schema_version:'foreground-collection-support-v1',mode:'four-platform-foreground-v1',public_source:'v2ex-latest-v1',
    public_sampling:'committed-round-v1',...(kind==='invalid'?{}:{public_monitor:true})}} as any;
  }return read(input);
 });
 expect(await f.controller.startMonitor({schema_version:'execution-runtime-v1',operation:'START',request_id:id(1),device_id:id(2),credential_version:1,
  profile_version_id:id(3),strategy_version_id:id(4),configuration_sha256:f.strategy.configuration_sha256,targets:f.command.targets})).toEqual({state:'SERVICE_UNAVAILABLE'});
 expect(f.execution.submit).not.toHaveBeenCalled();expect(f.worker.run).not.toHaveBeenCalled();
 expect(f.scope.transport.requestExecution.mock.calls.filter(([r])=>r.operation==='execution.support')).toHaveLength(1);
 await f.controller.shutdown();
});

it('rejects old, source-mismatched and wrong-device public monitor support before START',async()=>{
 for(const kind of ['old','source','device'] as const){const f=publicFixture();const c:any=f.strategy.snapshot.configuration;c.mode='monitor';c.schedule={kind:'interval',times:[],interval:1,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1};
  const hash=createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');f.strategy.configuration_sha256=hash;
  const read=f.scope.transport.requestExecution.getMockImplementation()!;f.scope.transport.requestExecution.mockImplementation(async input=>input.operation==='monitor.support'
   ?{ok:true,status:200,data:{schema_version:'monitor-runtime-support-v1',mode:'four-platform-monitor-v1',...(kind==='old'?{}:{public_source:kind==='source'?'other':'v2ex-latest-v1'})}}:read(input));
  const start={schema_version:'execution-runtime-v1',operation:'START',request_id:id(1),device_id:kind==='device'?id(99):id(2),credential_version:1,profile_version_id:id(3),strategy_version_id:id(4),configuration_sha256:hash,targets:f.command.targets};
  expect(await f.controller.validateMonitorBinding(id(3),id(4),start.targets as any)).toBe(kind==='device');
  expect(await f.controller.startMonitor(start)).toEqual({state:'SERVICE_UNAVAILABLE'});expect(f.execution.submit).not.toHaveBeenCalled();
 }
});

it.each(['three-platform-foreground-v1','xhs-foreground-v1'])('rejects Zhihu before START in %s',async mode=>{
 const f=fixture();f.command.targets[0].platform='ZHIHU';
 f.scope.transport.requestExecution.mockResolvedValue({ok:true,status:200,data:{schema_version:'foreground-collection-support-v1',mode}} as any);
 expect(await f.controller.start(f.command)).toEqual({state:'SERVICE_UNAVAILABLE'});
 expect(f.execution.submit).not.toHaveBeenCalled();expect(f.driverFactory).not.toHaveBeenCalled();
});
it.each(['three-platform-monitor-v1','four-platform-monitor-v1'])('Zhihu monitor dispatch respects %s',async mode=>{
 const f=fixture();f.command.targets[0].platform='ZHIHU';f.strategy.snapshot.platforms=['ZHIHU'];f.startReceipt.platform_runs[0].platform='ZHIHU';
 const c:any=f.strategy.snapshot.configuration;c.mode='monitor';c.schedule={kind:'daily',times:['09:30'],interval:1,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1};
 const hash=createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');f.strategy.configuration_sha256=hash;
 f.scope.transport.requestExecution.mockResolvedValue({ok:true,status:200,data:{schema_version:'monitor-runtime-support-v1',mode}} as any);
 f.resolveAccount.mockResolvedValue({profileId:id(30),accountPublicId:'123456'});
 const start={schema_version:'execution-runtime-v1',operation:'START',request_id:id(1),device_id:id(2),credential_version:1,profile_version_id:id(3),strategy_version_id:id(4),configuration_sha256:hash,targets:f.command.targets};
 expect(await f.controller.validateMonitorBinding(id(3),id(4),start.targets as any)).toBe(mode==='four-platform-monitor-v1');
 if(mode==='four-platform-monitor-v1'){
  expect(await f.controller.startMonitor(start)).toMatchObject({state:'RECORDED'});
  expect(f.driverFactory).toHaveBeenCalledWith(expect.objectContaining({allowMonitor:true,binding:expect.objectContaining({platform:'ZHIHU',expectedAccountPublicId:'123456'})}));
  f.finish();await f.controller.shutdown();
 }else{
  expect(await f.controller.startMonitor(start)).toEqual({state:'SERVICE_UNAVAILABLE'});
  expect(f.execution.submit).not.toHaveBeenCalled();expect(f.driverFactory).not.toHaveBeenCalled();
 }
});
