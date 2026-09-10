import type {YikeDesktopApi} from '../../shared/contracts';
import {monitorCollectionCommandSchema,monitorCollectionResultSchema,
 type MonitorCollectionCommand,type MonitorCollectionResult} from '../../shared/monitorCollection';
import {ServiceError} from './contracts';

export interface MonitorCollectionService {execute(command:MonitorCollectionCommand):Promise<MonitorCollectionResult>}
const cache=new WeakMap<YikeDesktopApi,MonitorCollectionService>();
export function monitorCollection(bridge:YikeDesktopApi|undefined):MonitorCollectionService|undefined {
 if(!bridge?.monitorCollectionCommand)return undefined;
 const known=cache.get(bridge);if(known)return known;
 const invoke=bridge.monitorCollectionCommand.bind(bridge);
 const service=Object.freeze({async execute(input:MonitorCollectionCommand):Promise<MonitorCollectionResult>{
  try{
   const command=monitorCollectionCommandSchema.parse(input);
   const result=monitorCollectionResultSchema.parse(await invoke(command));
   const original=command.action==='RECEIPT'?command.command:command;
   if(result.state==='LIST' && (command.action!=='LIST' || new Set(result.plans.map(p=>p.planId)).size!==result.plans.length))throw new Error();
   if(result.state==='UNKNOWN' && (!('requestId' in original) || result.requestId!==original.requestId))throw new Error();
   if(result.state==='RECORDED'){
    if(!('requestId' in original) || result.requestId!==original.requestId)throw new Error();
    if(original.action==='CREATE' && (result.plan.planId!==original.requestId || result.plan.profileVersionId!==original.profileVersionId ||
     result.plan.strategyVersionId!==original.strategyVersionId || result.plan.state!=='ACTIVE' || result.plan.revision!==1))throw new Error();
    if(original.action==='SET_STATE' && (result.plan.planId!==original.planId || result.plan.revision!==original.expectedRevision+1 || result.plan.state!==original.state))throw new Error();
   }
   if(result.state==='ATTACHED' && (command.action!=='ATTACH' || result.plan.planId!==command.planId || result.plan.revision!==command.expectedRevision || result.plan.state!=='ACTIVE'))throw new Error();
   return result;
  }catch{throw new ServiceError('MONITOR_RESPONSE_INVALID','监控响应未核实，原请求已保留；请核对结果，不要重新创建。');}
 }});cache.set(bridge,service);return service;
}
