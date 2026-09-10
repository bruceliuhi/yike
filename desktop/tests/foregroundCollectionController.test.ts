import {expect,it,vi} from 'vitest';
import {createHash} from 'node:crypto';
import {createForegroundCollectionController} from '../src/main/foregroundCollectionController';
const id=(n:number)=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
function canonical(v:any):string{return Array.isArray(v)?'['+v.map(canonical).join(',')+']':v&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}':JSON.stringify(v);}
function fixture(){
 let current=true;const requests:any[]=[];let resolveRun!:(value:any)=>void;
 const snapshot={profile_version_id:id(3),strategy_version_id:id(4),configuration:{schema_version:'research-strategy-v1',name:'原文',source:'search',keywords:['设计'],exclusions:[],links:[],mode:'once',schedule:null,research:null},platforms:['XIAOHONGSHU'],max_records:50,max_runtime_seconds:600};
 const hash=createHash('sha256').update(canonical(snapshot)).digest('hex');
 const strategy={schema_version:'strategy-confirmation-v1',strategy_version_id:id(4),profile_version_id:id(3),draft_id:id(10),draft_revision:1,profile_sha256:'b'.repeat(64),configuration_sha256:hash,snapshot,state:'CONFIRMED',created_at:'2026-09-10T00:00:00Z',confirmed_at:'2026-09-10T00:00:00Z',revoked_at:null,is_current:true,profile_current:true};
 const command={action:'START',humanConfirmed:true,requestId:id(1),profileVersionId:id(3),strategyVersionId:id(4),configurationSha256:hash,targets:[{platform:'XIAOHONGSHU',access_mode:'PLATFORM_ACCOUNT',connection_id:id(5),connection_version:2}]};
 const startReceipt={schema_version:'execution-runtime-v1',operation:'START',request_id:id(1),task_id:id(6),run_id:id(7),status:'PENDING',stop_confirmed:false,platform_runs:[{platform_run_id:id(8),platform:'XIAOHONGSHU',status:'PENDING'}]};
 const row={connection_id:id(5),device_id:id(2),platform:'XIAOHONGSHU',account_public_id:'66c01234abcdef0123456789',connection_version:2,status:'CONNECTED',connected_at:'2026-09-10T00:00:00Z',disconnected_at:null};
 const scope={device:{deviceId:id(2),credentialVersion:1},session:{userId:'owner',sessionId:id(20),isCurrent:()=>current},transport:{requestExecution:vi.fn(async(input:any)=>({ok:true,status:200,data:input.operation==='execution.support'?{schema_version:'foreground-collection-support-v1',mode:'xhs-foreground-v1'}:{task_id:id(6),run_id:id(7),status:'RUNNING',stop_confirmed:false,profile_version_id:id(3),strategy_version_id:id(4),max_records:50,records_used:0,deadline_at:'2026-09-10T00:10:00Z',platform_runs:[{platform_run_id:id(8),platform:'XIAOHONGSHU',status:'RUNNING',execution_generation:1,records_used:0}]}})),requestConnection:vi.fn(async()=>({ok:true,status:200,data:{items:[row]}})),requestCandidate:vi.fn()},close:vi.fn()};
 const identity={openWorkerScope:vi.fn(async()=>({ok:true,scope})),getStatus:()=>({state:'READY',...scope.device}),requestApi:vi.fn(async()=>({ok:true,status:200,data:strategy}))};
 const executionJournal={list:vi.fn(async()=>requests),read:vi.fn(async(_s:any,key:string)=>requests.find(r=>r.request_id===key)??null)};
 const candidatesJournal={list:vi.fn(async()=>[]),read:vi.fn()};
 const execution={submit:vi.fn(async(_s:any,r:any)=>{requests.push(r);return {state:'RECORDED',receipt:startReceipt};}),recover:vi.fn()};
 const worker={run:vi.fn((_input:any)=>new Promise(r=>resolveRun=r)),cancel:vi.fn()};
 const driverFactory=vi.fn(()=>({start:vi.fn()}));const resolveAccount=vi.fn(async()=>({profileId:id(30),accountPublicId:row.account_public_id}));const probe=vi.fn(async()=>true);
 const options:any={serviceOrigin:'https://pilot.example',identity,store:{read:vi.fn(async()=>({state:'RESOLVED',verification:{connection_id:id(5)}}))},executionJournal,candidateJournal:candidatesJournal,
  configuration:{pythonExecutable:'C:/python.exe',projectRoot:'C:/product',runtimePath:'C:/runtime',profileRoot:'C:/profiles',outputRoot:'C:/output'},
  sessions:()=>({execution,candidates:{recover:vi.fn()}}),workerFactory:()=>worker,driverFactory,resolveAccount,probe};
 return {controller:createForegroundCollectionController(options),options,identity,scope,requests,strategy,command,startReceipt,execution,executionJournal,candidatesJournal,worker,driverFactory,resolveAccount,probe,finish:(value:any={state:'COMPLETED',taskCompleted:true})=>resolveRun(value),invalidate:()=>current=false};
}
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
 const f=fixture();f.requests.push({...f.command,operation:'CLAIM',task_id:id(6),request_id:id(99)});
 expect(await f.controller.start(f.command)).toMatchObject({state:'RECORDED'});expect(f.worker.run).not.toHaveBeenCalled();
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
it('concurrent capability reads share one probe and bind only the protected current profile',async()=>{
 const f=fixture();const results=await Promise.all([f.controller.execute({action:'CAPABILITIES'}),f.controller.execute({action:'CAPABILITIES'})]);
 expect(results[0]).toEqual(results[1]);expect(results[0]).toMatchObject({state:'AVAILABLE',bindings:[{connectionId:id(5),deviceId:id(2)}]});
 expect(f.probe).toHaveBeenCalledTimes(1);expect(f.options.store.read).toHaveBeenCalledTimes(1);
});
it.each(['DOUYIN','BILIBILI'] as const)('starts selected %s target only in three-platform server mode',async platform=>{
 const f=fixture();const account=platform==='DOUYIN'?'douyin.account-1':'123456789';
 f.command.targets[0].platform=platform as any;f.strategy.snapshot.platforms=[platform] as any;
 const hash=createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');f.command.configurationSha256=hash;f.strategy.configuration_sha256=hash;
 f.scope.transport.requestExecution.mockImplementation(async(input:any)=>({ok:true,status:200,data:input.operation==='execution.support'
  ?{schema_version:'foreground-collection-support-v1',mode:'three-platform-foreground-v1'}
  :{task_id:id(6),run_id:id(7),status:'RUNNING',stop_confirmed:false,profile_version_id:id(3),strategy_version_id:id(4),max_records:50,records_used:0,deadline_at:'2026-09-10T00:10:00Z',platform_runs:[{platform_run_id:id(8),platform,status:'RUNNING',execution_generation:1,records_used:0}]}}));
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

it('STATUS accepts multiple platform candidate batches but keeps recovery conservative',async()=>{
 const f=fixture();(f.candidatesJournal.list as any).mockResolvedValue(['a','b']);
 (f.candidatesJournal.read as any).mockImplementation(async(_scope:any,key:string)=>({request_id:id(key==='a'?70:71),execution:{task_id:id(6)}}));
 expect(await f.controller.execute({action:'STATUS',taskId:id(6)})).toMatchObject({state:'STATUS',recordsUsed:0,recoverable:false});
});

it('monitor source stop failure latches the same foreground slot',async()=>{
 const f=fixture();const c:any=f.strategy.snapshot.configuration;c.mode='monitor';c.exclusions=['招聘'];c.schedule={kind:'interval',times:[],interval:1,start:'09:00',end:'18:00',timezone:'Asia/Shanghai',policyVersion:1};
 const hash=createHash('sha256').update(canonical(f.strategy.snapshot)).digest('hex');f.strategy.configuration_sha256=hash;
 (f.scope.transport.requestExecution as any).mockImplementation(async(input:any)=>input.operation==='monitor.support'?{ok:true,status:200,data:{schema_version:'monitor-runtime-support-v1',mode:'three-platform-monitor-v1'}}:{ok:false,status:400,error:'unexpected'});
 const start={schema_version:'execution-runtime-v1',operation:'START',request_id:id(1),device_id:id(2),credential_version:1,profile_version_id:id(3),strategy_version_id:id(4),configuration_sha256:hash,targets:f.command.targets};
 expect(await f.controller.startMonitor(start)).toMatchObject({state:'RECORDED'});f.finish({state:'FAILED',error:'SOURCE_STOP_FAILED',taskCompleted:false});await new Promise(resolve=>setImmediate(resolve));
 expect(f.controller.canStart()).toBe(false);await expect(f.controller.stop(id(6))).rejects.toThrow('SOURCE_STOP_FAILED');
 await expect(f.controller.shutdown()).rejects.toThrow('SOURCE_STOP_FAILED');
});
