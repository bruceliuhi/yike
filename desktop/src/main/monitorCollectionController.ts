import {randomUUID} from 'node:crypto';
import {z} from 'zod';
import {executionOperationSchema} from '../shared/executionOperation';
import {monitorCollectionCommandSchema,monitorScheduleSchema,type MonitorCollectionCommand,type MonitorCollectionPlan,type MonitorCollectionResult} from '../shared/monitorCollection';
import {deviceUuidSchema as uuid} from '../shared/deviceRegistration';
import type {DeviceWorkerScope} from './deviceIdentityController';

const planSchema=z.object({plan_id:uuid,profile_version_id:uuid,strategy_version_id:uuid,configuration_sha256:z.string().length(64).regex(/^[0-9a-f]{64}$/),
 schedule:monitorScheduleSchema,state:z.enum(['ACTIVE','PAUSED']),revision:z.number().int().min(1).max(2_147_483_647),next_due_at:z.string().datetime({offset:true}).nullable(),execution_status:z.literal('NOT_CONNECTED')}).strict();
const listSchema=z.object({schema_version:z.literal('monitor-plans-v1'),plans:z.array(planSchema).max(20),execution_status:z.literal('NOT_CONNECTED')}).strict();
const receiptSchema=z.object({schema_version:z.literal('monitor-plans-v1'),request_id:uuid,operation:z.enum(['CREATE','SET_STATE']),plan:planSchema,recorded_at:z.string().datetime({offset:true})}).strict();
const supportSchema=z.object({schema_version:z.literal('monitor-runtime-support-v1'),mode:z.literal('three-platform-monitor-v1').nullable()}).strict();
const occurrenceSchema=z.object({id:uuid,scheduled_at:z.string().datetime({offset:true}),expires_at:z.string().datetime({offset:true}),start_request:executionOperationSchema,task_id:uuid.nullable()}).strict();
const pulseSchema=z.object({schema_version:z.literal('monitor-runtime-v1'),plan_id:uuid,plan_revision:z.number().int().min(1),
 state:z.enum(['WAITING','READY','RUNNING','RECOVERY_REQUIRED','SKIPPED_OFFLINE','SKIPPED_MISSED','SKIPPED_BUSY']),server_time:z.string().datetime({offset:true}),
 next_due_at:z.string().datetime({offset:true}).nullable(),occurrence:occurrenceSchema.nullable()}).strict();
type Target=NonNullable<z.infer<typeof executionOperationSchema>['targets']>[number];
type Attachment={planId:string;revision:number;targets:Target[];userId:string;deviceId:string;credentialVersion:number;monitorSessionId:string;taskId:string|null;lastError:string|null;running:boolean};
interface Options{
 identity:{openWorkerScope():Promise<{ok:true;scope:DeviceWorkerScope}|{ok:false;state:string}>;getStatus():unknown};
  foreground:{canStart():boolean;validateMonitorBinding(profileId:string,strategyId:string,targets:Target[]):Promise<boolean>;
  startMonitor(start:unknown):Promise<unknown>;cancel(taskId?:string):void;stop?(taskId?:string):Promise<void>};intervalMs?:number;autoStart?:boolean;
}
const same=(a:unknown,b:unknown)=>JSON.stringify(a)===JSON.stringify(b);
export function createMonitorCollectionController(options:Options){
 const attached=new Map<string,Attachment>();let ticking=false,closed=false;let timer:ReturnType<typeof setInterval>|undefined;
 async function open(){const result=await options.identity.openWorkerScope();return result.ok?result.scope:null;}
 async function support(scope:DeviceWorkerScope){const result=await scope.transport.requestExecution({operation:'monitor.support'});return result.ok?supportSchema.parse(result.data).mode!==null:false;}
 async function plans(scope:DeviceWorkerScope){const result=await scope.transport.requestExecution({operation:'monitor.list'});if(!result.ok)throw new Error(result.error);return listSchema.parse(result.data).plans;}
 function published(plan:z.infer<typeof planSchema>,local?:Attachment):MonitorCollectionPlan{return {planId:plan.plan_id,profileVersionId:plan.profile_version_id,
  strategyVersionId:plan.strategy_version_id,configurationSha256:plan.configuration_sha256,schedule:plan.schedule,state:plan.state,revision:plan.revision,nextDueAt:plan.next_due_at,
  localState:local?(local.running?'RUNNING':'ATTACHED'):'DETACHED',taskId:local?.taskId??null,lastError:local?.lastError??null};}
 async function attach(scope:DeviceWorkerScope,plan:z.infer<typeof planSchema>,targets:Target[]){
  if(plan.state!=='ACTIVE'||!await options.foreground.validateMonitorBinding(plan.profile_version_id,plan.strategy_version_id,targets))return null;
  const value:Attachment={planId:plan.plan_id,revision:plan.revision,targets:structuredClone(targets),userId:scope.session.userId,deviceId:scope.device.deviceId,
   credentialVersion:scope.device.credentialVersion,monitorSessionId:randomUUID(),taskId:null,lastError:null,running:false};attached.set(plan.plan_id,value);return value;
 }
 const controller={
  async execute(raw:unknown):Promise<MonitorCollectionResult>{
   const parsed=monitorCollectionCommandSchema.safeParse(raw);if(!parsed.success)return {state:'INVALID_REQUEST'};const command=parsed.data;
   const scope=await open();if(!scope)return {state:'DEVICE_NOT_READY'};
   try{
    const supported=await support(scope);if(command.action==='LIST'){
     const values=await plans(scope);return {state:'LIST',supported,plans:values.map(p=>published(p,attached.get(p.plan_id))),serverTime:null};
    }
    if(!supported)return {state:'UNAVAILABLE'};
    if(command.action==='ATTACH'){
     const plan=(await plans(scope)).find(p=>p.plan_id===command.planId);if(!plan)return {state:'NOT_FOUND'};
     if(plan.revision!==command.expectedRevision)return {state:'CONFLICT'};const local=await attach(scope,plan,command.targets);return local?{state:'ATTACHED',plan:published(plan,local)}:{state:'CONFLICT'};
    }
    const original=command.action==='RECEIPT'?command.command:command;
    if(command.action==='CREATE'){
     if(!await options.foreground.validateMonitorBinding(command.profileVersionId,command.strategyVersionId,command.targets))return {state:'CONFLICT'};
     const response=await scope.transport.requestExecution({operation:'monitor.create',payload:{schema_version:'monitor-plans-v1',request_id:command.requestId,
      profile_version_id:command.profileVersionId,strategy_version_id:command.strategyVersionId,human_confirmed:true}});
     if(!response.ok)return response.status===0?{state:'UNKNOWN',requestId:command.requestId}:{state:'CONFLICT'};
     const receipt=receiptSchema.parse(response.data);if(receipt.request_id!==command.requestId||receipt.operation!=='CREATE')throw new Error();
     const local=await attach(scope,receipt.plan,command.targets);if(!local)throw new Error();return {state:'RECORDED',requestId:command.requestId,plan:published(receipt.plan,local)};
    }
    if(command.action==='RECEIPT'&&original.action==='CREATE'){
     const response=await scope.transport.requestExecution({operation:'monitor.receipt',payload:{request_id:original.requestId}});
     if(!response.ok)return {state:response.status===404?'NOT_FOUND':'SERVICE_UNAVAILABLE'};
     const receipt=receiptSchema.parse(response.data);if(receipt.request_id!==original.requestId||receipt.operation!=='CREATE'||
       receipt.plan.profile_version_id!==original.profileVersionId||receipt.plan.strategy_version_id!==original.strategyVersionId)return {state:'CONFLICT'};
     const local=await attach(scope,receipt.plan,original.targets);return local?{state:'RECORDED',requestId:original.requestId,plan:published(receipt.plan,local)}:{state:'CONFLICT'};
    }
    const stateCommand=original as Extract<MonitorCollectionCommand,{action:'SET_STATE'}>;const requestId=stateCommand.requestId;const response=command.action==='RECEIPT'
     ?await scope.transport.requestExecution({operation:'monitor.receipt',payload:{request_id:requestId}})
     :await (async()=>{if(stateCommand.state==='PAUSED'){const local=attached.get(stateCommand.planId);if(local){
       if(options.foreground.stop)await options.foreground.stop(local.taskId??undefined);else options.foreground.cancel(local.taskId??undefined);
     }}return scope.transport.requestExecution({operation:'monitor.state',payload:{schema_version:'monitor-plans-v1',request_id:requestId,plan_id:stateCommand.planId,
       expected_revision:stateCommand.expectedRevision,state:stateCommand.state,human_confirmed:true}});
      })();
    if(!response.ok)return response.status===0&&command.action!=='RECEIPT'?{state:'UNKNOWN',requestId}:{state:response.status===404?'NOT_FOUND':'CONFLICT'} as MonitorCollectionResult;
    const receipt=receiptSchema.parse(response.data);if(receipt.request_id!==requestId||receipt.operation!=='SET_STATE'||receipt.plan.plan_id!==stateCommand.planId)throw new Error();
    if(command.action==='RECEIPT'&&(!same(stateCommand.state,receipt.plan.state)||receipt.plan.revision!==stateCommand.expectedRevision+1))return {state:'CONFLICT'};
    if(stateCommand.state==='PAUSED'){const local=attached.get(stateCommand.planId);if(local){options.foreground.cancel(local.taskId??undefined);attached.delete(stateCommand.planId);}}
    let local:Attachment|undefined;if(stateCommand.state==='ACTIVE'&&stateCommand.targets)local=await attach(scope,receipt.plan,stateCommand.targets)??undefined;
    return {state:'RECORDED',requestId,plan:published(receipt.plan,local)};
   }catch{return {state:'SERVICE_UNAVAILABLE'};}finally{scope.close();}
  },
  async tick(){if(ticking||closed)return;ticking=true;try{for(const local of [...attached.values()]){
   const scope=await open();if(!scope){options.foreground.cancel(local.taskId??undefined);attached.delete(local.planId);continue;}
   try{
    if(!scope.session.isCurrent()||scope.session.userId!==local.userId||scope.device.deviceId!==local.deviceId||scope.device.credentialVersion!==local.credentialVersion){options.foreground.cancel(local.taskId??undefined);attached.delete(local.planId);continue;}
    const plan=(await plans(scope)).find(p=>p.plan_id===local.planId);if(!plan||plan.state!=='ACTIVE'||plan.revision!==local.revision){options.foreground.cancel(local.taskId??undefined);attached.delete(local.planId);continue;}
    const canStart=options.foreground.canStart();const response=await scope.transport.requestExecution({operation:'monitor.pulse',payload:{schema_version:'monitor-runtime-v1',plan_id:local.planId,
     device_id:local.deviceId,monitor_session_id:local.monitorSessionId,credential_version:local.credentialVersion,targets:local.targets,can_start:canStart}});
    if(!response.ok){local.lastError='SERVICE_UNAVAILABLE';continue;}const pulse=pulseSchema.parse(response.data);if(pulse.plan_id!==local.planId||pulse.plan_revision!==local.revision)throw new Error();
    local.taskId=pulse.occurrence?.task_id??null;local.running=pulse.state==='RUNNING';if(pulse.state==='RECOVERY_REQUIRED'){options.foreground.cancel(local.taskId??undefined);attached.delete(local.planId);continue;}
    if(pulse.state==='READY'&&canStart&&pulse.occurrence?.start_request){local.running=true;const result=await options.foreground.startMonitor(pulse.occurrence.start_request);
     if(!result||typeof result!=='object'||!('state' in result)||!['RECORDED','UNKNOWN'].includes(String(result.state)))local.lastError='MONITOR_START_FAILED';}
   }catch{local.lastError='MONITOR_PULSE_FAILED';}finally{scope.close();}
  }}finally{ticking=false;}},
  async shutdown(){closed=true;if(timer)clearInterval(timer);for(const local of attached.values())options.foreground.cancel(local.taskId??undefined);attached.clear();},
 };
 if(options.autoStart!==false)timer=setInterval(()=>{void controller.tick();},options.intervalMs??20_000);
 return controller;
}
