import {createHash,randomUUID} from 'node:crypto';
import {win32 as path} from 'node:path';
import {z} from 'zod';
import {desktopExecutionCommandSchema,type DesktopExecutionResult} from '../shared/desktopExecution';
import {executionOperationSchema} from '../shared/executionOperation';
import {parseExecutionReceipt} from '../shared/executionReceipt';
import {strategyViewSchema} from '../shared/researchStrategies';
import {connectionRegistryRowSchema} from '../shared/platformConnection';
import {foregroundCollectionCommandSchema,type ForegroundCollectionResult} from '../shared/foregroundCollection';
import {deviceUuidSchema as uuid} from '../shared/deviceRegistration';
import type {createDeviceIdentityController,DeviceWorkerScope} from './deviceIdentityController';
import type {ExecutionJournal} from './executionJournal';
import type {CandidateJournal} from './candidateJournal';
import type {createExecutionSession} from './executionSession';
import type {createCandidateSession} from './candidateSession';
import type {createConnectionProfileStore} from './connectionProfileStore';
import type {PlatformLoginDriverOptions} from './platformLoginDriver';
import {createCollectionWorker,type CollectionWorkerResult} from './collectionWorker';
import {createPythonCollectionDriver} from './pythonCollectionDriver';
import {resolveCollectionAccount} from './collectionAccountBinding';
import {probeCollectionRuntime} from './collectionRuntimeProbe';
import {nativeLoginPlatformSchema,type NativeLoginPlatform} from '../shared/platformAccount';

interface Options {
 serviceOrigin:string;
 identity:Pick<ReturnType<typeof createDeviceIdentityController>,'openWorkerScope'|'getStatus'|'requestApi'>;
 store:Pick<ReturnType<typeof createConnectionProfileStore>,'read'>;
 executionJournal:Pick<ExecutionJournal,'list'|'read'>;
 candidateJournal:Pick<CandidateJournal,'list'|'read'>;
 configuration:PlatformLoginDriverOptions;
 sessions(scope:DeviceWorkerScope):{execution:ReturnType<typeof createExecutionSession>;candidates:ReturnType<typeof createCandidateSession>};
 workerFactory?:typeof createCollectionWorker; driverFactory?:typeof createPythonCollectionDriver;
 resolveAccount?:typeof resolveCollectionAccount;probe?:typeof probeCollectionRuntime;
}
const supportSchema=z.object({schema_version:z.literal('foreground-collection-support-v1'),mode:z.enum(['xhs-foreground-v1','three-platform-foreground-v1']).nullable()}).strict();
const rowsSchema=z.object({items:z.array(connectionRegistryRowSchema).max(10000)}).strict();
const stateSchema=z.enum(['PENDING','RUNNING','CANCELLING','CANCELED','SUCCEEDED']);
const taskSchema=z.object({task_id:uuid,run_id:uuid,status:stateSchema,stop_confirmed:z.boolean(),profile_version_id:uuid,strategy_version_id:uuid,
 max_records:z.number().int().positive(),records_used:z.number().int().min(0),deadline_at:z.string().datetime({offset:true}),
 platform_runs:z.array(z.object({platform_run_id:uuid,platform:z.enum(['XIAOHONGSHU','DOUYIN','BILIBILI','ZHIHU','PUBLIC_WEB']),status:stateSchema,
  execution_generation:z.number().int().min(0),records_used:z.number().int().min(0)}).strict()).min(1).max(5)}).strict();
function canonical(v:unknown):string{return Array.isArray(v)?'['+v.map(canonical).join(',')+']':v&&typeof v==='object'
 ?'{'+Object.entries(v).sort(([a],[b])=>a<b?-1:a>b?1:0).map(([k,x])=>JSON.stringify(k)+':'+canonical(x)).join(',')+'}':JSON.stringify(v);}

/** Single foreground run. Existing immutable CLAIM/upload journals are restart markers, not new authority. */
export function createForegroundCollectionController(options:Options) {
 const {identity,serviceOrigin,configuration}=options;
 let opening=false,shuttingDown=false,stopUnconfirmed=false;
 let openingDone:Promise<void>|null=null,finishOpening:(()=>void)|null=null;
 let capabilityPending:Promise<ForegroundCollectionResult>|null=null;
 type Active={taskId:string;userId:string;scope:DeviceWorkerScope;worker:ReturnType<typeof createCollectionWorker>;done:Promise<void>};
 let active:Active|null=null;
 const local=new Map<string,CollectionWorkerResult>();
 const localKey=(scope:DeviceWorkerScope,taskId:string)=>JSON.stringify([scope.session.userId,scope.session.sessionId,taskId]);
 const journalScope=(scope:DeviceWorkerScope)=>({serviceOrigin,userId:scope.session.userId});
 function guard(scope:DeviceWorkerScope){
  const status=identity.getStatus();
  if(shuttingDown || !scope.session.isCurrent() || status.state!=='READY' || status.deviceId!==scope.device.deviceId || status.credentialVersion!==scope.device.credentialVersion)throw new Error('COLLECTION_UNAVAILABLE');
 }
 async function open(){
  const result=await identity.openWorkerScope();if(!result.ok)throw new Error('COLLECTION_UNAVAILABLE');
  const original=result.scope;
  const scope={...original,session:{...original.session,isCurrent:()=>{
   const observed=identity.getStatus();return !shuttingDown && original.session.isCurrent() && observed.state==='READY' &&
    observed.deviceId===original.device.deviceId && observed.credentialVersion===original.device.credentialVersion;
  }}};
  try{guard(scope);return scope;}catch(error){scope.close();throw error;}
 }
 async function supported(scope:DeviceWorkerScope){
  if(stopUnconfirmed)throw new Error('SOURCE_STOP_FAILED');
  guard(scope);const response=await scope.transport.requestExecution({operation:'execution.support'});guard(scope);
  if(!response.ok)throw new Error('COLLECTION_UNAVAILABLE');const support=supportSchema.safeParse(response.data);
  if(!support.success || support.data.mode===null)throw new Error('COLLECTION_UNAVAILABLE');
  if(!await (options.probe??probeCollectionRuntime)(configuration))throw new Error('COLLECTION_UNAVAILABLE');guard(scope);
  return support.data.mode;
 }
 async function account(scope:DeviceWorkerScope,target:unknown,extra:object={}){
  guard(scope);const value=await (options.resolveAccount??resolveCollectionAccount)({serviceOrigin,scope,store:options.store,target,...extra});guard(scope);return value;
 }
 async function capabilities():Promise<ForegroundCollectionResult>{
  let scope:DeviceWorkerScope|undefined;
  try{
   scope=await open();const mode=await supported(scope);
   const response=await scope.transport.requestConnection({operation:'connections.current'});guard(scope);if(!response.ok)throw new Error();
   const rows=rowsSchema.parse(response.data).items;if(new Set(rows.map(row=>row.connection_id)).size!==rows.length)throw new Error();
   const platforms:NativeLoginPlatform[]=['XIAOHONGSHU','DOUYIN','BILIBILI'];
   const bindings=[];
   for(const platform of platforms){
    if(mode==='xhs-foreground-v1' && platform!=='XIAOHONGSHU')continue;
    try{
     const record=await options.store.read({serviceOrigin,userId:scope.session.userId,deviceId:scope.device.deviceId,platform});guard(scope);
     if(record?.state!=='RESOLVED')continue;
     const row=rows.find(r=>r.connection_id===record.verification?.connection_id && r.platform===platform && r.device_id===scope!.device.deviceId && r.status==='CONNECTED');
     if(!row)continue;
     const binding=await account(scope,{platform:row.platform,access_mode:'PLATFORM_ACCOUNT',connection_id:row.connection_id,connection_version:row.connection_version},
      {protectedRecord:record,currentRows:{items:rows}});
     if(binding.accountPublicId!==row.account_public_id)continue;guard(scope);
     bindings.push({mode,platform,connectionId:row.connection_id,connectionVersion:row.connection_version,deviceId:row.device_id,accountPublicId:row.account_public_id});
    }catch{guard(scope);}
   }
   return bindings.length?{state:'AVAILABLE',bindings}:{state:'UNAVAILABLE'};
  }catch{return {state:'UNAVAILABLE'};}finally{scope?.close();}
 }
 async function task(scope:DeviceWorkerScope,taskId:string){
  guard(scope);const response=await scope.transport.requestExecution({operation:'execution.task',payload:{task_id:taskId}});guard(scope);
  if(!response.ok)throw new Error();const value=taskSchema.parse(response.data);
  if(value.task_id!==taskId || new Set(value.platform_runs.map(p=>p.platform_run_id)).size!==value.platform_runs.length ||
   value.records_used!==value.platform_runs.reduce((n,p)=>n+p.records_used,0) || value.status==='SUCCEEDED' && (!value.stop_confirmed || value.platform_runs.some(p=>p.status!=='SUCCEEDED')))throw new Error();
  return value;
 }
 async function batchFor(scope:DeviceWorkerScope,taskId:string){
  const keys=await options.candidateJournal.list(journalScope(scope));guard(scope);
  let found:Awaited<ReturnType<CandidateJournal['read']>>=null;
  for(const key of keys){const batch=await options.candidateJournal.read(journalScope(scope),key);guard(scope);
   if(batch?.execution.task_id===taskId){if(found)throw new Error();found=batch;}}
  return found;
 }
 async function status(scope:DeviceWorkerScope,taskId:string):Promise<ForegroundCollectionResult>{
  const current=await task(scope,taskId),batch=await batchFor(scope,taskId);guard(scope);
  const running=active?.taskId===taskId && active.userId===scope.session.userId && active.scope.session.sessionId===scope.session.sessionId;
  const result=local.get(localKey(scope,taskId));
  const localState=running?'COLLECTING':result?.state==='COMPLETED'?'COMPLETED':result?.state==='UPLOAD_UNKNOWN'?'UPLOAD_UNKNOWN':result?.state==='FINISH_UNKNOWN'?'FINISH_UNKNOWN':result?.state==='STOPPED'?'STOPPED':result?.state==='FAILED'?'FAILED':'INTERRUPTED';
  return {state:'STATUS',taskId,localState,serverStatus:current.status,stopConfirmed:current.stop_confirmed,recordsUsed:current.records_used,
   recoverable:!running && !!batch && !['CANCELED','CANCELLING','SUCCEEDED'].includes(current.status)};
 }
 const controller={
  canStart(){return !opening&&!active&&!shuttingDown&&!stopUnconfirmed;},
  async stop(taskId?:string){const current=active;if(!current||taskId&&current.taskId!==taskId)return;current.worker.cancel();await current.done;},
  async validateMonitorBinding(profileId:string,strategyId:string,targets:NonNullable<import('../shared/executionOperation').ExecutionOperation['targets']>):Promise<boolean>{
   let scope:DeviceWorkerScope|undefined;
   try{
    scope=await open();const support=await scope.transport.requestExecution({operation:'monitor.support'});guard(scope);
    if(!support.ok||supportSchema.safeParse({schema_version:'foreground-collection-support-v1',mode:support.data&&typeof support.data==='object'&&'mode' in support.data&&support.data.mode==='three-platform-monitor-v1'?'three-platform-foreground-v1':null}).data?.mode)throw new Error();
    if(!await (options.probe??probeCollectionRuntime)(configuration))throw new Error();
    const response=await identity.requestApi({operation:'strategies.get',payload:{strategy_version_id:strategyId}});guard(scope);if(!response.ok)throw new Error();
    const strategy=strategyViewSchema.parse(response.data),snapshot=strategy.snapshot,c=snapshot.configuration;
    if(strategy.state!=='CONFIRMED'||!strategy.is_current||!strategy.profile_current||strategy.confirmed_at===null||strategy.revoked_at!==null||
      strategy.profile_version_id!==profileId||snapshot.profile_version_id!==profileId||strategy.strategy_version_id!==strategyId||snapshot.strategy_version_id!==strategyId||
      c.mode!=='monitor'||c.schedule?.policyVersion!==1||snapshot.platforms.length!==targets.length||targets.some((target,index)=>target.platform!==snapshot.platforms[index])||
      targets.some(target=>!nativeLoginPlatformSchema.safeParse(target.platform).success||target.access_mode!=='PLATFORM_ACCOUNT'))throw new Error();
    for(const target of targets)await account(scope,target);
    return true;
   }catch{return false;}finally{scope?.close();}
  },
  async startMonitor(raw:unknown):Promise<DesktopExecutionResult>{
   const parsed=executionOperationSchema.safeParse(raw);if(!parsed.success||parsed.data.operation!=='START')return {state:'INVALID_REQUEST'};
   if(opening||active)return {state:'BUSY'};if(shuttingDown||stopUnconfirmed)return {state:'SERVICE_UNAVAILABLE'};
   opening=true;openingDone=new Promise(resolve=>{finishOpening=resolve;});let scope:DeviceWorkerScope|undefined,handedOff=false;
   try{
    const start=parsed.data,targets=start.targets!;scope=await open();
    const monitorSupport=await scope.transport.requestExecution({operation:'monitor.support'});guard(scope);
    if(!monitorSupport.ok||!monitorSupport.data||typeof monitorSupport.data!=='object'||(monitorSupport.data as any).schema_version!=='monitor-runtime-support-v1'||(monitorSupport.data as any).mode!=='three-platform-monitor-v1')throw new Error();
    if(!await (options.probe??probeCollectionRuntime)(configuration))throw new Error();guard(scope);
    const strategyResponse=await identity.requestApi({operation:'strategies.get',payload:{strategy_version_id:start.strategy_version_id}});guard(scope);if(!strategyResponse.ok)throw new Error();
    const strategy=strategyViewSchema.parse(strategyResponse.data),snapshot=strategy.snapshot,c=snapshot.configuration;
    if(strategy.state!=='CONFIRMED'||!strategy.is_current||!strategy.profile_current||strategy.confirmed_at===null||strategy.revoked_at!==null||
      strategy.profile_version_id!==start.profile_version_id||strategy.strategy_version_id!==start.strategy_version_id||snapshot.profile_version_id!==start.profile_version_id||
      snapshot.strategy_version_id!==start.strategy_version_id||strategy.configuration_sha256!==start.configuration_sha256||createHash('sha256').update(canonical(snapshot)).digest('hex')!==start.configuration_sha256||
      c.mode!=='monitor'||c.schedule?.policyVersion!==1||c.source!=='search'||c.research!==null||c.links.length||c.exclusions.length||
      snapshot.platforms.length!==targets.length||targets.some((target,index)=>target.platform!==snapshot.platforms[index]||target.access_mode!=='PLATFORM_ACCOUNT'||!nativeLoginPlatformSchema.safeParse(target.platform).success))throw new Error();
    const bindings=[];for(const target of targets)bindings.push(await account(scope,target));
    const firstSessions=options.sessions(scope);const submitted=await firstSessions.execution.submit(scope.session,start);guard(scope);if(submitted.state!=='RECORDED')return submitted;
    const receipt=parseExecutionReceipt(submitted.receipt,start);if(receipt.operation!=='START'||receipt.platform_runs.length!==targets.length||receipt.platform_runs.some((run,index)=>run.platform!==targets[index].platform))throw new Error();
    const history=await options.executionJournal.list(journalScope(scope));guard(scope);if(history.some(r=>r.task_id===receipt.task_id&&r.operation!=='START'))return submitted;
    let currentWorker:ReturnType<typeof createCollectionWorker>|null=null,cancelled=false;
    const composite={cancel(){cancelled=true;currentWorker?.cancel();}} as ReturnType<typeof createCollectionWorker>;
    const current:Active={taskId:receipt.task_id,userId:scope.session.userId,scope,worker:composite,done:Promise.resolve()};active=current;handedOff=true;
    current.done=(async()=>{
      let activeScope:DeviceWorkerScope|undefined=scope;scope=undefined;
      try{for(let index=0;index<targets.length;index++){
        if(cancelled)break;if(index>0){const opened=await open();if(opened.session.userId!==current.userId||opened.device.deviceId!==current.scope.device.deviceId||opened.device.credentialVersion!==current.scope.device.credentialVersion){opened.close();break;}activeScope=opened;}
        const binding=index===0?bindings[index]:await account(activeScope!,targets[index]);const sessions=index===0?firstSessions:options.sessions(activeScope!);
        const driver=(options.driverFactory??createPythonCollectionDriver)({pythonExecutable:configuration.pythonExecutable,projectRoot:configuration.projectRoot,runtimePath:configuration.runtimePath,
          profilePath:path.join(configuration.profileRoot,binding.profileId),outputRoot:configuration.outputRoot,allowMonitor:true,
          binding:{...activeScope!.device,...targets[index],expectedAccountPublicId:binding.accountPublicId}});
        currentWorker=(options.workerFactory??createCollectionWorker)({...sessions,driver});
        const value=await currentWorker.run({scope:activeScope!,start,startReceipt:receipt,strategy,platformRunId:receipt.platform_runs[index].platform_run_id,allowMonitor:true});
        local.set(localKey(current.scope,receipt.task_id),value);activeScope=undefined;if(value.state!=='COMPLETED'||!value.taskCompleted&&index===targets.length-1)break;
      }}catch{activeScope?.close();}finally{if(active===current)active=null;}
    })();
    return submitted;
   }catch{return {state:'SERVICE_UNAVAILABLE'};}finally{if(!handedOff)scope?.close();opening=false;finishOpening?.();finishOpening=null;openingDone=null;}
  },
  // Main calls this only after an explicitly approved original START recovery.
  async resumeStart(requestId:string):Promise<DesktopExecutionResult>{
   let scope:DeviceWorkerScope|undefined;
   let command:unknown;
   try{
    scope=await open();const raw=await options.executionJournal.read(journalScope(scope),uuid.parse(requestId));guard(scope);
    if(!raw)return {state:'NOT_FOUND'};const original=executionOperationSchema.parse(raw);
    if(original.operation!=='START' || original.device_id!==scope.device.deviceId || original.credential_version!==scope.device.credentialVersion)throw new Error();
    command={action:'START',humanConfirmed:true,requestId:original.request_id,profileVersionId:original.profile_version_id,
     strategyVersionId:original.strategy_version_id,configurationSha256:original.configuration_sha256,targets:original.targets};
   }catch{return {state:'SERVICE_UNAVAILABLE'};}finally{scope?.close();}
   return controller.start(command);
  },
  async start(raw:unknown):Promise<DesktopExecutionResult>{
   const parsed=desktopExecutionCommandSchema.safeParse(raw);if(!parsed.success || parsed.data.action!=='START')return {state:'INVALID_REQUEST'};
   if(opening || active)return {state:'BUSY'};if(shuttingDown || stopUnconfirmed)return {state:'SERVICE_UNAVAILABLE'};
   opening=true;openingDone=new Promise(resolve=>{finishOpening=resolve;});let scope:DeviceWorkerScope|undefined,handedOff=false;
   try{
    const command=parsed.data;
    if(command.targets.length!==1 || !nativeLoginPlatformSchema.safeParse(command.targets[0].platform).success || command.targets[0].access_mode!=='PLATFORM_ACCOUNT')throw new Error();
    scope=await open();const mode=await supported(scope);const target=command.targets[0];
    if(mode==='xhs-foreground-v1' && target.platform!=='XIAOHONGSHU')throw new Error();
    const binding=await account(scope,target);
    const response=await identity.requestApi({operation:'strategies.get',payload:{strategy_version_id:command.strategyVersionId}});guard(scope);if(!response.ok)throw new Error();
    const strategy=strategyViewSchema.parse(response.data),snapshot=strategy.snapshot,c=snapshot.configuration;
    if(strategy.state!=='CONFIRMED' || !strategy.is_current || !strategy.profile_current || strategy.confirmed_at===null || strategy.revoked_at!==null ||
     strategy.profile_version_id!==command.profileVersionId || strategy.strategy_version_id!==command.strategyVersionId ||
     snapshot.profile_version_id!==command.profileVersionId || snapshot.strategy_version_id!==command.strategyVersionId ||
     strategy.configuration_sha256!==command.configurationSha256 || createHash('sha256').update(canonical(snapshot)).digest('hex')!==command.configurationSha256 ||
     snapshot.platforms.length!==1 || snapshot.platforms[0]!==target.platform || snapshot.max_records>100 || snapshot.max_runtime_seconds>900 ||
     c.mode!=='once' || c.source!=='search' || c.schedule!==null || c.research!==null || c.links.length || c.exclusions.length || c.keywords.some(k=>k!==k.trim() || k.includes(',')))throw new Error();
    const start=executionOperationSchema.parse({schema_version:'execution-runtime-v1',operation:'START',request_id:command.requestId,
     device_id:scope.device.deviceId,credential_version:scope.device.credentialVersion,profile_version_id:command.profileVersionId,strategy_version_id:command.strategyVersionId,
     configuration_sha256:command.configurationSha256,targets:command.targets});
    const sessions=options.sessions(scope);const result=await sessions.execution.submit(scope.session,start);guard(scope);
    if(result.state!=='RECORDED')return result;
    const receipt=parseExecutionReceipt(result.receipt,start);if(receipt.operation!=='START')throw new Error();
    const history=await options.executionJournal.list(journalScope(scope));guard(scope);
    // Even a CLAIM whose response was lost can have started a source before a crash.
    if(history.some(r=>r.task_id===receipt.task_id && r.operation!=='START'))return result;
    const driver=(options.driverFactory??createPythonCollectionDriver)({pythonExecutable:configuration.pythonExecutable,projectRoot:configuration.projectRoot,runtimePath:configuration.runtimePath,
     profilePath:path.join(configuration.profileRoot,binding.profileId),outputRoot:configuration.outputRoot,
     binding:{...scope.device,...command.targets[0],expectedAccountPublicId:binding.accountPublicId}});
    const worker=(options.workerFactory??createCollectionWorker)({...sessions,driver});
    const current:Active={taskId:receipt.task_id,userId:scope.session.userId,scope,worker,done:Promise.resolve()};active=current;handedOff=true;
    current.done=worker.run({scope,start,startReceipt:receipt,strategy,platformRunId:receipt.platform_runs[0].platform_run_id}).then(value=>{
     if(value.state==='FAILED' && value.error==='SOURCE_STOP_FAILED')stopUnconfirmed=true;
     local.set(localKey(current.scope,current.taskId),value);
    },()=>{local.set(localKey(current.scope,current.taskId),{state:'FAILED',error:'COLLECTION_WORKER_FAILED',taskCompleted:false});}).finally(()=>{
     current.scope.close();if(active===current)active=null;
    });
    return result;
   }catch{return {state:'SERVICE_UNAVAILABLE'};}finally{if(!handedOff)scope?.close();opening=false;finishOpening?.();finishOpening=null;openingDone=null;}
  },
  async execute(raw:unknown):Promise<ForegroundCollectionResult>{
   const parsed=foregroundCollectionCommandSchema.safeParse(raw);if(!parsed.success)return {state:'INVALID_REQUEST'};
   const command=parsed.data;
   if(command.action==='CAPABILITIES'){
    if(!capabilityPending)capabilityPending=capabilities().finally(()=>{capabilityPending=null;});return capabilityPending;
   }
   if(opening || active && command.action==='RECOVER')return {state:'BUSY'};
   if(command.action==='RECOVER'){opening=true;openingDone=new Promise(resolve=>{finishOpening=resolve;});}
   let scope:DeviceWorkerScope|undefined;
   try{
    scope=await open();
    if(command.action==='RECOVER'){
     await task(scope,command.taskId);const batch=await batchFor(scope,command.taskId);guard(scope);if(!batch)return {state:'NOT_FOUND'};
     if(batch.execution.device_id!==scope.device.deviceId || batch.execution.credential_version!==scope.device.credentialVersion)throw new Error();
     const sessions=options.sessions(scope);
     const uploaded=await sessions.candidates.recover(scope.session,{platformRunId:batch.execution.platform_run_id,requestId:batch.request_id},command.retry??false);guard(scope);
     if(uploaded.state==='RECORDED'){
      const history=await options.executionJournal.list(journalScope(scope));guard(scope);
      const finishes=history.filter(r=>r.operation==='FINISH' && r.task_id===command.taskId && r.platform_run_id===batch.execution.platform_run_id && r.upload_request_id===batch.request_id);
      if(finishes.length>1)throw new Error();
      // Candidate journals are written only after physical source stop. Resume only this immutable batch, never the browser.
      const original=finishes[0];
      const request=original??executionOperationSchema.parse({schema_version:'execution-runtime-v1',operation:'FINISH',request_id:randomUUID(),
       device_id:batch.execution.device_id,credential_version:batch.execution.credential_version,task_id:batch.execution.task_id,platform_run_id:batch.execution.platform_run_id,
       lease_id:batch.execution.lease_id,execution_generation:batch.execution.execution_generation,upload_request_id:batch.request_id});
      const finish=original?await sessions.execution.recover(scope.session,original.request_id,command.retry??false):await sessions.execution.submit(scope.session,request);guard(scope);
      if(finish.state==='RECORDED'){
       const receipt=parseExecutionReceipt(finish.receipt,request);if(receipt.operation!=='FINISH')throw new Error();
       local.set(localKey(scope,command.taskId),{state:'COMPLETED',taskCompleted:receipt.status==='SUCCEEDED' && receipt.stop_confirmed,requestId:request.request_id,
        recoveryKey:{platformRunId:batch.execution.platform_run_id,requestId:batch.request_id}});
      }
     }
    }
    return await status(scope,command.taskId);
   }catch{return {state:'UNAVAILABLE'};}finally{
    scope?.close();if(command.action==='RECOVER'){opening=false;finishOpening?.();finishOpening=null;openingDone=null;}
   }
  },
  cancel(taskId:string){if(active?.taskId===taskId)active.worker.cancel();},
  async shutdown(){shuttingDown=true;await openingDone;active?.worker.cancel();const current=active;await current?.done;
   if(stopUnconfirmed)throw new Error('SOURCE_STOP_FAILED');
  },
 };
 return controller;
}
