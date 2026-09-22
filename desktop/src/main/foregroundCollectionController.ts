import {createHash,randomUUID} from 'node:crypto';
import {win32 as path} from 'node:path';
import {z} from 'zod';
import {desktopExecutionCommandSchema,type DesktopExecutionResult} from '../shared/desktopExecution';
import {executionOperationSchema} from '../shared/executionOperation';
import {parseExecutionReceipt} from '../shared/executionReceipt';
import {strategyViewSchema} from '../shared/researchStrategies';
import {connectionRegistryRowSchema} from '../shared/platformConnection';
import {foregroundCollectionCommandSchema,foregroundModeSchema,nativeLinkPlatformsSchema,supportsForegroundPlatform,monitorForegroundMode,monitorSupportSchema,type ForegroundCollectionResult} from '../shared/foregroundCollection';
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
import {createPublicCommunityDriver} from './publicCommunityDriver';
import {resolveCollectionAccount} from './collectionAccountBinding';
import {probeCollectionRuntime} from './collectionRuntimeProbe';
import {nativeLoginPlatformSchema,type NativeLoginPlatform} from '../shared/platformAccount';
import {allowsPublicSource,publicSourceIdSchema,publicSourceIdsSchema,validPublicSourceCatalog} from '../shared/publicSources';
import {planNativeCollectionLinks} from '../shared/nativeCollectionLinks';

interface Options {
 serviceOrigin:string;
 identity:Pick<ReturnType<typeof createDeviceIdentityController>,'openWorkerScope'|'getStatus'|'requestApi'>;
 store:Pick<ReturnType<typeof createConnectionProfileStore>,'read'>;
 executionJournal:Pick<ExecutionJournal,'list'|'read'|'persist'>;
 candidateJournal:Pick<CandidateJournal,'list'|'read'>;
 configuration:PlatformLoginDriverOptions|null;
 sessions(scope:DeviceWorkerScope):{execution:ReturnType<typeof createExecutionSession>;candidates:ReturnType<typeof createCandidateSession>};
 workerFactory?:typeof createCollectionWorker; driverFactory?:typeof createPythonCollectionDriver;
 publicDriverFactory?:typeof createPublicCommunityDriver;
 resolveAccount?:typeof resolveCollectionAccount;probe?:typeof probeCollectionRuntime;
}
const supportSchema=z.object({schema_version:z.literal('foreground-collection-support-v1'),mode:foregroundModeSchema.nullable(),
 public_source:z.literal('v2ex-latest-v1').optional(),public_sources:publicSourceIdsSchema.optional(),public_monitor:z.literal(true).optional(),native_links:nativeLinkPlatformsSchema.optional(),
 public_sampling:z.enum(['committed-round-v1','committed-round-revisit-v2']).optional(),native_progress:z.tuple([z.literal('BILIBILI')]).optional()})
 .strict().refine(value=>validPublicSourceCatalog(value.public_source,value.public_sources))
 .refine(value=>value.public_sampling===undefined||value.public_monitor===true&&value.public_source!==undefined)
 .refine(value=>value.native_progress===undefined||supportsForegroundPlatform(value.mode,'BILIBILI'))
 .refine(value=>(value.mode==='four-platform-public-bili-links-monitor-v1')===(value.native_links!==undefined));
const rowsSchema=z.object({items:z.array(connectionRegistryRowSchema).max(10000)}).strict();
const stateSchema=z.enum(['PENDING','RUNNING','CANCELLING','CANCELED','SUCCEEDED']);
const taskSchema=z.object({task_id:uuid,run_id:uuid,status:stateSchema,stop_confirmed:z.boolean(),profile_version_id:uuid,strategy_version_id:uuid,
 max_records:z.number().int().positive(),records_used:z.number().int().min(0),deadline_at:z.string().datetime({offset:true}),
 platform_runs:z.array(z.object({platform_run_id:uuid,platform:z.enum(['XIAOHONGSHU','DOUYIN','BILIBILI','ZHIHU','PUBLIC_WEB']),status:stateSchema,
  execution_generation:z.number().int().min(0),records_used:z.number().int().min(0)}).strict()).min(1).max(5)}).strict();
function canonical(v:unknown):string{return Array.isArray(v)?'['+v.map(canonical).join(',')+']':v&&typeof v==='object'
 ?'{'+Object.entries(v).sort(([a],[b])=>a<b?-1:a>b?1:0).map(([k,x])=>JSON.stringify(k)+':'+canonical(x)).join(',')+'}':JSON.stringify(v);}
function nativeLinkScope(snapshot:any,targets:any[],declared:readonly string[]|undefined):boolean {
 try{return snapshot.configuration.source==='links'&&snapshot.configuration.research===null&&declared?.length===1&&declared[0]==='BILIBILI'&&
  targets.length===1&&targets[0].platform==='BILIBILI'&&targets[0].access_mode==='PLATFORM_ACCOUNT'&&
  planNativeCollectionLinks(snapshot.platforms,snapshot.configuration.links).every(item=>item.platform==='BILIBILI'&&
   (item.kind==='creator'||/^BV1[1-9A-HJ-NP-Za-km-z]{9}$/.test(item.external_id)))&&
  snapshot.max_records>=snapshot.configuration.links.length;}catch{return false;}
}

/** Single foreground run. Existing immutable CLAIM/upload journals are restart markers, not new authority. */
export function createForegroundCollectionController(options:Options) {
 const {identity,serviceOrigin}=options;
 let configuration=options.configuration?structuredClone(options.configuration):null;
 let publicDriver:ReturnType<typeof createPublicCommunityDriver>|null=null;
 let opening=false,shuttingDown=false,stopUnconfirmed=false;
 let openingDone:Promise<void>|null=null,finishOpening:(()=>void)|null=null;
 let scopeOpening:Promise<void>=Promise.resolve();
 let capabilityPending:Promise<ForegroundCollectionResult>|null=null;
 type Active={taskId:string;userId:string;scope:DeviceWorkerScope;worker:ReturnType<typeof createCollectionWorker>;done:Promise<void>};
 let active:Active|null=null;
 const local=new Map<string,CollectionWorkerResult>();
 const reconcilingStops=new Set<string>();
 const cancelOrigins=new Map<string,{userId:string;sessionId:string;deviceId:string;credentialVersion:number}>();
 const localKey=(scope:DeviceWorkerScope,taskId:string)=>JSON.stringify([scope.session.userId,scope.session.sessionId,taskId]);
 const journalScope=(scope:DeviceWorkerScope)=>({serviceOrigin,userId:scope.session.userId});
 function guard(scope:DeviceWorkerScope){
  const status=identity.getStatus();
  if(shuttingDown || !scope.session.isCurrent() || status.state!=='READY' || status.deviceId!==scope.device.deviceId || status.credentialVersion!==scope.device.credentialVersion)throw new Error('COLLECTION_UNAVAILABLE');
 }
 async function open(){
  // STATUS/capability reads share the identity controller's short opening
  // mutex with the next platform. Queue only acquisition, not source work.
  const previous=scopeOpening;let release!:()=>void;
  scopeOpening=new Promise<void>(resolve=>{release=resolve;});
  await previous;
  try{if(shuttingDown)throw new Error('COLLECTION_UNAVAILABLE');return await openScope();}
  finally{release();}
 }
 async function openScope(){
  const result=await identity.openWorkerScope();if(!result.ok)throw new Error('COLLECTION_UNAVAILABLE');
  const original=result.scope;
  const scope={...original,session:{...original.session,isCurrent:()=>{
   const observed=identity.getStatus();return !shuttingDown && original.session.isCurrent() && observed.state==='READY' &&
    observed.deviceId===original.device.deviceId && observed.credentialVersion===original.device.credentialVersion;
  }}};
  try{guard(scope);return scope;}catch(error){scope.close();throw error;}
 }
 async function supported(scope:DeviceWorkerScope,samplingVersion?:1|2,progressVersion?:1){
  if(stopUnconfirmed)throw new Error('SOURCE_STOP_FAILED');
  guard(scope);let response=await scope.transport.requestExecution({operation:'execution.support',...(samplingVersion?{samplingVersion}:{}),...(progressVersion?{progressVersion}:{})});guard(scope);
  const legacyProgress=progressVersion===1&&!response.ok&&response.status===422&&response.error==='invalid_request';
  const legacySampling=samplingVersion===2&&!response.ok&&response.status===422&&response.error==='invalid_request';
  if(legacyProgress){
   // Previous servers explicitly reject unknown query keys. Only this read-only
   // capability rejection permits one plain read; never retry execution/unknowns.
   response=await scope.transport.requestExecution({operation:'execution.support'});guard(scope);
  }
  if(legacySampling){
   response=await scope.transport.requestExecution({operation:'execution.support',samplingVersion:1});guard(scope);
  }
  if(!response.ok)throw new Error('COLLECTION_UNAVAILABLE');const support=supportSchema.safeParse(response.data);
  if(!support.success || support.data.mode===null)throw new Error('COLLECTION_UNAVAILABLE');
  if(legacyProgress)delete support.data.native_progress;
  if(legacySampling&&support.data.public_sampling==='committed-round-revisit-v2')throw new Error('COLLECTION_UNAVAILABLE');
  return support.data;
 }
 async function nativeReady(scope:DeviceWorkerScope){
  if(!configuration || !await (options.probe??probeCollectionRuntime)(configuration))throw new Error('COLLECTION_UNAVAILABLE');guard(scope);
 }
 async function account(scope:DeviceWorkerScope,target:unknown,extra:object={}){
  guard(scope);const value=await (options.resolveAccount??resolveCollectionAccount)({serviceOrigin,scope,store:options.store,target,...extra});guard(scope);return value;
 }
 async function capabilities():Promise<ForegroundCollectionResult>{
  let scope:DeviceWorkerScope|undefined;
  try{
   scope=await open();const support=await supported(scope),mode=support.mode!;
   const publicBinding=support.public_source?{sourceId:support.public_source,...(support.public_sources?{sourceIds:support.public_sources}:{}),deviceId:scope.device.deviceId,...(support.public_monitor===true?{monitorSupported:true as const}:{})}:undefined;
   const publicOnly=():ForegroundCollectionResult=>publicBinding?{state:'AVAILABLE',bindings:[],publicBinding}:{state:'UNAVAILABLE'};
   try{await nativeReady(scope);}catch{guard(scope);return publicOnly();}
   // Public readiness is independent of the native account registry, but not
   // of the authenticated service/device scope above.
   try{
   const response=await scope.transport.requestConnection({operation:'connections.current'});guard(scope);if(!response.ok)throw new Error();
   const rows=rowsSchema.parse(response.data).items;if(new Set(rows.map(row=>row.connection_id)).size!==rows.length)throw new Error();
   const platforms:NativeLoginPlatform[]=['XIAOHONGSHU','DOUYIN','BILIBILI','ZHIHU'];
   const bindings=[];
   for(const platform of platforms){
    if(!supportsForegroundPlatform(mode,platform))continue;
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
   const linkPlatforms=support.native_links&&bindings.some(binding=>binding.platform==='BILIBILI')?support.native_links:undefined;
   return bindings.length||publicBinding?{state:'AVAILABLE',bindings,...(publicBinding?{publicBinding}:{}),...(linkPlatforms?{linkPlatforms}:{})}:{state:'UNAVAILABLE'};
   }catch{guard(scope);return publicOnly();}
  }catch{return {state:'UNAVAILABLE'};}finally{scope?.close();}
 }
 async function task(scope:DeviceWorkerScope,taskId:string){
  guard(scope);const response=await scope.transport.requestExecution({operation:'execution.task',payload:{task_id:taskId}});guard(scope);
  if(!response.ok)throw new Error();const value=taskSchema.parse(response.data);
  if(value.task_id!==taskId || new Set(value.platform_runs.map(p=>p.platform_run_id)).size!==value.platform_runs.length ||
   value.records_used!==value.platform_runs.reduce((n,p)=>n+p.records_used,0) || value.status==='SUCCEEDED' && (!value.stop_confirmed || value.platform_runs.some(p=>p.status!=='SUCCEEDED')))throw new Error();
  return value;
 }
 async function batchesFor(scope:DeviceWorkerScope,taskId:string){
  const keys=await options.candidateJournal.list(journalScope(scope));guard(scope);
  const found:NonNullable<Awaited<ReturnType<CandidateJournal['read']>>>[]=[];
  for(const key of keys){const batch=await options.candidateJournal.read(journalScope(scope),key);guard(scope);
   if(batch?.execution.task_id===taskId)found.push(batch);}
  return found;
 }
 async function status(scope:DeviceWorkerScope,taskId:string):Promise<ForegroundCollectionResult>{
  let current=await task(scope,taskId);const batches=await batchesFor(scope,taskId);guard(scope);
  current=await reconcileStops(scope,current,batches);
  const running=active?.taskId===taskId && active.userId===scope.session.userId && active.scope.session.sessionId===scope.session.sessionId;
  const result=local.get(localKey(scope,taskId));
  const localState=running?'COLLECTING':result?.state==='COMPLETED'&&result.taskCompleted?'COMPLETED':result?.state==='UPLOAD_UNKNOWN'?'UPLOAD_UNKNOWN':result?.state==='FINISH_UNKNOWN'||result?.state==='COMPLETED'?'FINISH_UNKNOWN':result?.state==='STOPPED'?'STOPPED':result?.state==='FAILED'?'FAILED':'INTERRUPTED';
  return {state:'STATUS',taskId,localState,serverStatus:current.status,stopConfirmed:current.stop_confirmed,recordsUsed:current.records_used,
   recoverable:!running && batches.length>0 && !['CANCELED','CANCELLING','SUCCEEDED'].includes(current.status)};
 }
 async function reconcileStops(scope:DeviceWorkerScope,current:Awaited<ReturnType<typeof task>>,batches:Awaited<ReturnType<typeof batchesFor>>){
  if(current.status!=='CANCELLING')return current;
  const history=await options.executionJournal.list(journalScope(scope));guard(scope);
  for(const raw of history){
   if(raw.operation!=='STOP'||raw.task_id!==current.task_id)continue;
   const request=executionOperationSchema.parse(raw),platform=current.platform_runs.find(p=>p.platform_run_id===request.platform_run_id);
   if(!platform||platform.platform==='PUBLIC_WEB'||platform.status!=='CANCELLING'||platform.execution_generation!==request.execution_generation||
    request.device_id!==scope.device.deviceId||request.credential_version!==scope.device.credentialVersion||
    batches.some(b=>b.execution.platform_run_id===request.platform_run_id)||
    history.some(r=>r.operation==='FINISH'&&r.task_id===current.task_id&&r.platform_run_id===request.platform_run_id)||reconcilingStops.has(request.request_id))continue;
   reconcilingStops.add(request.request_id);
   try{
    guard(scope);const result=await options.sessions(scope).execution.recover(scope.session,request.request_id,true,
     {deviceId:request.device_id,credentialVersion:request.credential_version});guard(scope);
    if(result.state!=='RECORDED')continue;
    const receipt=parseExecutionReceipt(result.receipt,request);
    if(receipt.operation!=='STOP'||receipt.run_id!==current.run_id)throw new Error();
    // Historical receipt is not current aggregate state; read the authoritative task again.
    current=await task(scope,current.task_id);
   }finally{reconcilingStops.delete(request.request_id);}
  }
  return current;
 }
 function budgets(total:number,count:number){
  if(!Number.isInteger(total)||total<count)throw new Error();const base=Math.floor(total/count),extra=total%count;
  return Array.from({length:count},(_,index)=>base+(index<extra?1:0));
 }
 function launchSequence(input:{scope:DeviceWorkerScope;start:any;receipt:any;strategy:any;targets:any[];bindings:any[];firstSessions:any;allowMonitor?:boolean;allowPublicSampling?:true|2;allowNativeProgress?:true;allowNativeLinks?:true;startIndex?:number}){
  let currentWorker:ReturnType<typeof createCollectionWorker>|null=null,cancelled=false;
  const composite={cancel(){cancelled=true;currentWorker?.cancel();}} as ReturnType<typeof createCollectionWorker>;
  const current:Active={taskId:input.receipt.task_id,userId:input.scope.session.userId,scope:input.scope,worker:composite,done:Promise.resolve()};
  const original={userId:input.scope.session.userId,sessionId:input.scope.session.sessionId,...input.scope.device};
  active=current;const allocated=budgets(input.strategy.snapshot.max_records,input.targets.length);
  current.done=(async()=>{let activeScope:DeviceWorkerScope|undefined=input.scope;
   try{for(let index=input.startIndex??0;index<input.targets.length;index++){
    if(cancelled)break;if(index>(input.startIndex??0)){const opened=await open();if(cancelled||!opened.session.isCurrent()||opened.session.userId!==current.userId||opened.session.sessionId!==current.scope.session.sessionId||opened.device.deviceId!==current.scope.device.deviceId||opened.device.credentialVersion!==current.scope.device.credentialVersion){opened.close();break;}activeScope=opened;}
    const anonymous=input.targets[index].platform==='PUBLIC_WEB';
    const binding=anonymous?null:index===(input.startIndex??0)?input.bindings[index]:await account(activeScope!,input.targets[index]);
    if(cancelled||!activeScope!.session.isCurrent()){activeScope!.close();activeScope=undefined;break;}
    const sessions=index===(input.startIndex??0)?input.firstSessions:options.sessions(activeScope!);
    let driver:ReturnType<typeof createPublicCommunityDriver>;
    if(anonymous){
     if(!publicSourceIdSchema.safeParse(input.strategy.snapshot.configuration.publicSource).success)throw new Error();
     if(index>(input.startIndex??0)){const live=input.allowMonitor
      ?await activeScope!.transport.requestExecution({operation:'monitor.support'}):await activeScope!.transport.requestExecution({operation:'execution.support'});
      guard(activeScope!);const parsed=input.allowMonitor?monitorSupportSchema.safeParse(live.ok?live.data:null):supportSchema.safeParse(live.ok?live.data:null);
      if(!parsed.success||!allowsPublicSource(input.strategy.snapshot.configuration.publicSource,parsed.data.public_source,parsed.data.public_sources))throw new Error();}
     if(cancelled||!activeScope!.session.isCurrent()){activeScope!.close();activeScope=undefined;break;}
     publicDriver??=(options.publicDriverFactory??createPublicCommunityDriver)();driver=publicDriver;
    }else{
     if(!configuration)throw new Error();
     driver=(options.driverFactory??createPythonCollectionDriver)({pythonExecutable:configuration.pythonExecutable,projectRoot:configuration.projectRoot,runtimePath:configuration.runtimePath,
      profilePath:path.join(configuration.profileRoot,binding.profileId),outputRoot:configuration.outputRoot,allowMonitor:input.allowMonitor,
      ...(input.allowNativeLinks?{allowNativeLinks:true as const}:{}),
      binding:{...activeScope!.device,...input.targets[index],expectedAccountPublicId:binding.accountPublicId}});
    }
    currentWorker=(options.workerFactory??createCollectionWorker)({...sessions,driver});
    const value=await currentWorker.run({scope:activeScope!,start:input.start,startReceipt:input.receipt,strategy:input.strategy,
     platformRunId:input.receipt.platform_runs[index].platform_run_id,allowMonitor:input.allowMonitor,platformMaxRecords:allocated[index],
     ...(anonymous&&input.allowPublicSampling?{allowPublicSampling:input.allowPublicSampling}:{}),
     ...(input.targets[index].platform==='BILIBILI'&&input.allowNativeProgress?{allowNativeProgress:true as const}:{})});
    if(value.state==='FAILED'&&value.error==='SOURCE_STOP_FAILED')stopUnconfirmed=true;
    local.set(localKey(current.scope,current.taskId),value);activeScope=undefined;
    if(!anonymous&&value.state==='STOPPED'&&value.reason==='CANCELLED'&&value.stopProof){
     const proof=value.stopProof;
     if(proof.taskId===current.taskId&&proof.platformRunId===input.receipt.platform_runs[index].platform_run_id&&
       proof.deviceId===original.deviceId&&proof.credentialVersion===original.credentialVersion){
      let fresh:DeviceWorkerScope|undefined;
      try{
       const request=executionOperationSchema.parse({schema_version:'execution-runtime-v1',operation:'STOP',request_id:randomUUID(),
        device_id:proof.deviceId,credential_version:proof.credentialVersion,task_id:proof.taskId,platform_run_id:proof.platformRunId,
        lease_id:proof.leaseId,execution_generation:proof.executionGeneration});
       const saved=await options.executionJournal.persist({serviceOrigin,userId:original.userId},request);
       if(JSON.stringify(saved.request)!==JSON.stringify(request))throw new Error();
       fresh=await open();
       if(fresh.session.userId!==original.userId||fresh.session.sessionId!==original.sessionId||fresh.device.deviceId!==original.deviceId||
         fresh.device.credentialVersion!==original.credentialVersion)throw new Error();
       await status(fresh,current.taskId);
      }catch{/* Physical stop is local evidence only; retain journal/uncertainty for later reconciliation. */}
      finally{fresh?.close();}
     }
    }
    if(value.state==='COMPLETED')continue;
    // A platform-level source/lease failure must not prevent the remaining
    // platforms in the same confirmed round from running. Unknown upload or
    // finish receipts still stop the round so recovery can reconcile the
    // current platform before another source is started; global cancellation,
    // session changes and an unconfirmed physical stop always stop as well.
    const continueAfterFailure = value.state === 'FAILED' || value.state === 'LEASE_UNKNOWN' ||
      value.state === 'STOPPED' && (value.reason === 'LEASE_EXPIRED' || value.reason === 'LEASE_UNKNOWN');
    if(!continueAfterFailure || cancelled || stopUnconfirmed)break;
   }}catch{activeScope?.close();local.set(localKey(current.scope,current.taskId),{state:'FAILED',error:'COLLECTION_WORKER_FAILED',taskCompleted:false});}
   finally{if(active===current)active=null;}})();
 }
 const controller={
  // Bootstrap may finish during an anonymous run. Install native paths once,
  // never replace the controller/journals or mutate a running native binding.
  configureNativeRuntime(value:PlatformLoginDriverOptions){if(!configuration&&!shuttingDown)configuration=structuredClone(value);},
  canStart(){return !opening&&!active&&!shuttingDown&&!stopUnconfirmed;},
  async stop(taskId?:string){const current=active;if(!current||taskId&&current.taskId!==taskId){if(stopUnconfirmed)throw new Error('SOURCE_STOP_FAILED');return;}
   current.worker.cancel();await current.done;if(stopUnconfirmed)throw new Error('SOURCE_STOP_FAILED');},
  async validateMonitorBinding(profileId:string,strategyId:string,targets:NonNullable<import('../shared/executionOperation').ExecutionOperation['targets']>):Promise<boolean>{
   let scope:DeviceWorkerScope|undefined;
   try{
    scope=await open();const support=await scope.transport.requestExecution({operation:'monitor.support'});guard(scope);
    const parsedSupport=monitorSupportSchema.safeParse(support.ok?support.data:null),mode=monitorForegroundMode(support.ok?support.data:null);
    if(!support.ok||!parsedSupport.success||!mode||targets.some(target=>target.platform==='PUBLIC_WEB'
      ?target.access_mode!=='PUBLIC_ANONYMOUS'||target.connection_id!==null||target.connection_version!==null||parsedSupport.data.public_source!=='v2ex-latest-v1'
      :!supportsForegroundPlatform(mode,target.platform)))throw new Error();
    if(targets.some(target=>target.platform!=='PUBLIC_WEB'))await nativeReady(scope);
    const response=await identity.requestApi({operation:'strategies.get',payload:{strategy_version_id:strategyId}});guard(scope);if(!response.ok)throw new Error();
    const strategy=strategyViewSchema.parse(response.data),snapshot=strategy.snapshot,c=snapshot.configuration;
    const links=nativeLinkScope(snapshot,targets,parsedSupport.data.native_links);
    if(strategy.state!=='CONFIRMED'||!strategy.is_current||!strategy.profile_current||strategy.confirmed_at===null||strategy.revoked_at!==null||
      strategy.profile_version_id!==profileId||snapshot.profile_version_id!==profileId||strategy.strategy_version_id!==strategyId||snapshot.strategy_version_id!==strategyId||
      c.mode!=='monitor'||c.schedule?.policyVersion!==1||snapshot.max_records<targets.length||snapshot.max_records>100||snapshot.max_runtime_seconds>900||
      c.research!==null||!links&&(c.source!=='search'||c.links.length>0||c.keywords.some(k=>k!==k.trim()||k.includes(',')))||
      snapshot.platforms.length!==targets.length||targets.some((target,index)=>target.platform!==snapshot.platforms[index])||
      targets.some(target=>target.platform==='PUBLIC_WEB'?!allowsPublicSource(c.publicSource,parsedSupport.data.public_source,parsedSupport.data.public_sources):
       !nativeLoginPlatformSchema.safeParse(target.platform).success||target.access_mode!=='PLATFORM_ACCOUNT'))throw new Error();
    for(const target of targets)if(target.platform!=='PUBLIC_WEB')await account(scope,target);
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
    const parsedSupport=monitorSupportSchema.safeParse(monitorSupport.ok?monitorSupport.data:null),mode=monitorForegroundMode(monitorSupport.ok?monitorSupport.data:null);
    if(!monitorSupport.ok||!parsedSupport.success||!mode||start.device_id!==scope.device.deviceId||start.credential_version!==scope.device.credentialVersion||targets.some(target=>target.platform==='PUBLIC_WEB'
      ?target.access_mode!=='PUBLIC_ANONYMOUS'||target.connection_id!==null||target.connection_version!==null||parsedSupport.data.public_source!=='v2ex-latest-v1'
      :!supportsForegroundPlatform(mode,target.platform)))throw new Error();
    if(targets.some(target=>target.platform!=='PUBLIC_WEB'))await nativeReady(scope);
    const strategyResponse=await identity.requestApi({operation:'strategies.get',payload:{strategy_version_id:start.strategy_version_id}});guard(scope);if(!strategyResponse.ok)throw new Error();
    const strategy=strategyViewSchema.parse(strategyResponse.data),snapshot=strategy.snapshot,c=snapshot.configuration;
    const links=nativeLinkScope(snapshot,targets,parsedSupport.data.native_links);
    if(strategy.state!=='CONFIRMED'||!strategy.is_current||!strategy.profile_current||strategy.confirmed_at===null||strategy.revoked_at!==null||
      strategy.profile_version_id!==start.profile_version_id||strategy.strategy_version_id!==start.strategy_version_id||snapshot.profile_version_id!==start.profile_version_id||
      snapshot.strategy_version_id!==start.strategy_version_id||strategy.configuration_sha256!==start.configuration_sha256||createHash('sha256').update(canonical(snapshot)).digest('hex')!==start.configuration_sha256||
      c.mode!=='monitor'||c.schedule?.policyVersion!==1||snapshot.max_records<targets.length||snapshot.max_records>100||snapshot.max_runtime_seconds>900||c.research!==null||!links&&(c.source!=='search'||c.links.length>0||c.keywords.some(k=>k!==k.trim()||k.includes(',')))||
      snapshot.platforms.length!==targets.length||targets.some((target,index)=>target.platform!==snapshot.platforms[index]||
       (target.platform==='PUBLIC_WEB'?!allowsPublicSource(c.publicSource,parsedSupport.data.public_source,parsedSupport.data.public_sources):target.access_mode!=='PLATFORM_ACCOUNT'||!nativeLoginPlatformSchema.safeParse(target.platform).success)))throw new Error();
    let allowPublicSampling:true|2|undefined;
    let allowNativeProgress:true|undefined;
    if(c.source==='search'&&targets.some(target=>target.platform==='BILIBILI')){
     const progress=await supported(scope,undefined,1);
     if(progress.native_progress?.includes('BILIBILI'))allowNativeProgress=true;
    }
    if(targets.some(target=>target.platform==='PUBLIC_WEB')){
     const sampling=await supported(scope,2);
     if(!allowsPublicSource(c.publicSource,sampling.public_source,sampling.public_sources))throw new Error();
     if(sampling.public_sampling==='committed-round-v1')allowPublicSampling=true;
     if(sampling.public_sampling==='committed-round-revisit-v2')allowPublicSampling=2;
    }
    const bindings=[];for(const target of targets)bindings.push(target.platform==='PUBLIC_WEB'?null:await account(scope,target));
    const firstSessions=options.sessions(scope);const submitted=await firstSessions.execution.submit(scope.session,start);guard(scope);if(submitted.state!=='RECORDED')return submitted;
    const receipt=parseExecutionReceipt(submitted.receipt,start);if(receipt.operation!=='START'||receipt.platform_runs.length!==targets.length||receipt.platform_runs.some((run,index)=>run.platform!==targets[index].platform))throw new Error();
    const history=await options.executionJournal.list(journalScope(scope));guard(scope);if(history.some(r=>r.task_id===receipt.task_id&&r.operation!=='START'))return submitted;
    launchSequence({scope,start,receipt,strategy,targets,bindings,firstSessions,allowMonitor:true,...(allowPublicSampling?{allowPublicSampling}:{}),...(allowNativeProgress?{allowNativeProgress}:{}),...(links?{allowNativeLinks:true as const}:{})});scope=undefined;handedOff=true;
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
    scope=await open();const support=await supported(scope);
    const hasPublic=command.targets.some(target=>target.platform==='PUBLIC_WEB');
    if(command.targets.some(target=>target.platform==='PUBLIC_WEB'
     ?support.public_source!=='v2ex-latest-v1'||target.access_mode!=='PUBLIC_ANONYMOUS'||target.connection_id!==null||target.connection_version!==null
     :!supportsForegroundPlatform(support.mode,target.platform)||target.access_mode!=='PLATFORM_ACCOUNT'))throw new Error();
    if(command.targets.some(target=>target.platform!=='PUBLIC_WEB'))await nativeReady(scope);
    const bindings=[];for(const target of command.targets)bindings.push(target.platform==='PUBLIC_WEB'?null:await account(scope,target));
    const response=await identity.requestApi({operation:'strategies.get',payload:{strategy_version_id:command.strategyVersionId}});guard(scope);if(!response.ok)throw new Error();
    const strategy=strategyViewSchema.parse(response.data),snapshot=strategy.snapshot,c=snapshot.configuration;
    const links=nativeLinkScope(snapshot,command.targets,support.native_links);
    if(strategy.state!=='CONFIRMED' || !strategy.is_current || !strategy.profile_current || strategy.confirmed_at===null || strategy.revoked_at!==null ||
     strategy.profile_version_id!==command.profileVersionId || strategy.strategy_version_id!==command.strategyVersionId ||
     snapshot.profile_version_id!==command.profileVersionId || snapshot.strategy_version_id!==command.strategyVersionId ||
     strategy.configuration_sha256!==command.configurationSha256 || createHash('sha256').update(canonical(snapshot)).digest('hex')!==command.configurationSha256 ||
     snapshot.platforms.length!==command.targets.length || command.targets.some((target,index)=>snapshot.platforms[index]!==target.platform) ||
     snapshot.max_records<command.targets.length || snapshot.max_records>100 || snapshot.max_runtime_seconds>900 ||
     c.mode!=='once' || c.schedule!==null || c.research!==null || !links&&(c.source!=='search'||c.links.length>0||c.keywords.some(k=>k!==k.trim() || k.includes(','))) ||
     hasPublic && !allowsPublicSource(c.publicSource,support.public_source,support.public_sources) || !hasPublic && c.publicSource!==undefined)throw new Error();
    const start=executionOperationSchema.parse({schema_version:'execution-runtime-v1',operation:'START',request_id:command.requestId,
     device_id:scope.device.deviceId,credential_version:scope.device.credentialVersion,profile_version_id:command.profileVersionId,strategy_version_id:command.strategyVersionId,
     configuration_sha256:command.configurationSha256,targets:command.targets});
    const sessions=options.sessions(scope);const result=await sessions.execution.submit(scope.session,start);guard(scope);
    if(result.state!=='RECORDED')return result;
    const receipt=parseExecutionReceipt(result.receipt,start);if(receipt.operation!=='START'||receipt.platform_runs.length!==command.targets.length||receipt.platform_runs.some((run,index)=>run.platform!==command.targets[index].platform))throw new Error();
    const history=await options.executionJournal.list(journalScope(scope));guard(scope);
    // Local absence is never evidence that a source was not executed: bind every launch to current generation zero.
    const taskHistory=history.filter(r=>r.task_id===receipt.task_id&&r.operation!=='START');
    const currentTask=await task(scope,receipt.task_id),batches=await batchesFor(scope,receipt.task_id);guard(scope);
    if(currentTask.run_id!==receipt.run_id||currentTask.profile_version_id!==start.profile_version_id||currentTask.strategy_version_id!==start.strategy_version_id||
      currentTask.max_records!==snapshot.max_records||currentTask.platform_runs.length!==receipt.platform_runs.length||Date.parse(currentTask.deadline_at)<=Date.now()||
      ['CANCELED','CANCELLING','SUCCEEDED'].includes(currentTask.status))throw new Error();
    const currentById=new Map(currentTask.platform_runs.map(run=>[run.platform_run_id,run]));
    if(currentById.size!==receipt.platform_runs.length)throw new Error();
    const ordered=receipt.platform_runs.map((original,index)=>{const run=currentById.get(original.platform_run_id);
      if(!run||run.platform!==original.platform||run.platform!==command.targets[index].platform)return null;return run;});
    if(ordered.some(run=>run===null))throw new Error();let startIndex=ordered.findIndex(run=>run!.status!=='SUCCEEDED');
    if(startIndex<0)throw new Error();
    for(let index=0;index<ordered.length;index++){
     const run=ordered[index]!,runOps=taskHistory.filter(item=>item.platform_run_id===run.platform_run_id),runBatches=batches.filter(batch=>batch.execution.platform_run_id===run.platform_run_id);
     if(index<startIndex){
      if(run.status!=='SUCCEEDED'||run.execution_generation<1||runBatches.length!==1)throw new Error();const batch=runBatches[0];
      if(batch.platform!==run.platform||batch.execution.run_id!==receipt.run_id||batch.execution.device_id!==scope.device.deviceId||
       batch.execution.credential_version!==scope.device.credentialVersion||batch.execution.execution_generation!==run.execution_generation||
       runOps.filter(item=>item.operation==='CLAIM').length!==1)throw new Error();
      const finishes=runOps.filter(item=>item.operation==='FINISH'&&item.upload_request_id===batch.request_id);if(finishes.length!==1)throw new Error();
      const recovered=await sessions.execution.recover(scope.session,finishes[0].request_id,false,scope.device);guard(scope);
      if(recovered.state!=='RECORDED'){return result;}const verified=parseExecutionReceipt(recovered.receipt,finishes[0]);
      if(verified.operation!=='FINISH'||verified.run_id!==receipt.run_id||verified.platform_run_id!==run.platform_run_id)throw new Error();
     }else if(run.status!=='PENDING'||run.execution_generation!==0||run.records_used!==0||runOps.length||runBatches.length)throw new Error();
    }
    launchSequence({scope,start,receipt,strategy,targets:command.targets,bindings,firstSessions:sessions,startIndex,...(links?{allowNativeLinks:true as const}:{})});scope=undefined;handedOff=true;
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
     const currentTask=await task(scope,command.taskId),batches=await batchesFor(scope,command.taskId);guard(scope);if(!batches.length)return {state:'NOT_FOUND'};
     const runOrder=new Map(currentTask.platform_runs.map((run,index)=>[run.platform_run_id,index]));batches.sort((left,right)=>runOrder.get(left.execution.platform_run_id)!-runOrder.get(right.execution.platform_run_id)!);
     const history=await options.executionJournal.list(journalScope(scope));guard(scope);
     const seen=new Set<string>(),seenRuns=new Set<string>(),seenRequests=new Set<string>();const plans:{batch:(typeof batches)[number];original:any}[]=[];
     for(const batch of batches){
     const mapping=JSON.stringify([batch.execution.platform_run_id,batch.request_id]);
     const serverRun=currentTask.platform_runs.find(run=>run.platform_run_id===batch.execution.platform_run_id);
     if(seen.has(mapping)||seenRuns.has(batch.execution.platform_run_id)||seenRequests.has(batch.request_id)||batch.execution.task_id!==command.taskId||batch.execution.run_id!==currentTask.run_id||
       batch.profile_version_id!==currentTask.profile_version_id||batch.strategy_version_id!==currentTask.strategy_version_id||!serverRun||batch.platform!==serverRun.platform||
       batch.execution.execution_generation!==serverRun.execution_generation||
       batch.execution.device_id!==scope.device.deviceId || batch.execution.credential_version!==scope.device.credentialVersion)throw new Error();seen.add(mapping);
     seenRuns.add(batch.execution.platform_run_id);seenRequests.add(batch.request_id);
     const finishes=history.filter(r=>r.operation==='FINISH'&&r.task_id===command.taskId&&r.platform_run_id===batch.execution.platform_run_id&&r.upload_request_id===batch.request_id);
     if(finishes.length>1)throw new Error();const original=finishes[0];
     if(original&&(original.device_id!==batch.execution.device_id||original.credential_version!==batch.execution.credential_version||original.lease_id!==batch.execution.lease_id||original.execution_generation!==batch.execution.execution_generation))throw new Error();
     plans.push({batch,original});
     }
     for(const {batch,original} of plans){
     const sessions=options.sessions(scope);
     const uploaded=await sessions.candidates.recover(scope.session,{platformRunId:batch.execution.platform_run_id,requestId:batch.request_id},command.retry??false);guard(scope);
     if(uploaded.state!=='RECORDED')break;
      // Candidate journals are written only after physical source stop. Resume only this immutable batch, never the browser.
      const request=original??executionOperationSchema.parse({schema_version:'execution-runtime-v1',operation:'FINISH',request_id:randomUUID(),
       device_id:batch.execution.device_id,credential_version:batch.execution.credential_version,task_id:batch.execution.task_id,platform_run_id:batch.execution.platform_run_id,
       lease_id:batch.execution.lease_id,execution_generation:batch.execution.execution_generation,upload_request_id:batch.request_id});
      const finish=original?await sessions.execution.recover(scope.session,original.request_id,command.retry??false,scope.device):await sessions.execution.submit(scope.session,request);guard(scope);
      if(finish.state!=='RECORDED')break;
       const receipt=parseExecutionReceipt(finish.receipt,request);if(receipt.operation!=='FINISH')throw new Error();
       local.set(localKey(scope,command.taskId),{state:'COMPLETED',taskCompleted:receipt.status==='SUCCEEDED' && receipt.stop_confirmed,requestId:request.request_id,
       recoveryKey:{platformRunId:batch.execution.platform_run_id,requestId:batch.request_id}});
    }
    }
    return await status(scope,command.taskId);
   }catch{return {state:'UNAVAILABLE'};}finally{
    scope?.close();if(command.action==='RECOVER'){opening=false;finishOpening?.();finishOpening=null;openingDone=null;}
   }
  },
  cancel(taskId:string){if(active?.taskId===taskId){
   cancelOrigins.set(taskId,{userId:active.userId,sessionId:active.scope.session.sessionId,...active.scope.device});
   active.worker.cancel();
  }},
  async acknowledgeCancellation(taskId:string){
   // Called after server CANCEL, independently of the worker's proof persistence.
   // Worker completion never waits on this callback, so awaiting it cannot form a cycle.
   const original=cancelOrigins.get(taskId),current=active;
   if(current?.taskId===taskId)await current.done;
   let fresh:DeviceWorkerScope|undefined;
   try{
    fresh=await open();
    if(original&&(fresh.session.userId!==original.userId||fresh.session.sessionId!==original.sessionId||
      fresh.device.deviceId!==original.deviceId||fresh.device.credentialVersion!==original.credentialVersion))throw new Error();
    return await status(fresh,taskId);
   }catch{return {state:'UNAVAILABLE'} as ForegroundCollectionResult;}
   finally{fresh?.close();if(cancelOrigins.get(taskId)===original)cancelOrigins.delete(taskId);}
  },
  async shutdown(){shuttingDown=true;await openingDone;active?.worker.cancel();const current=active;await current?.done;
   if(stopUnconfirmed)throw new Error('SOURCE_STOP_FAILED');
  },
 };
 return controller;
}
