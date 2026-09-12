import {researchRuntimeCapabilitySchema,researchRuntimeStatusSchema,researchRuntimeStatusRequestSchema,
  researchRuntimeAdvanceRequestSchema,type ResearchRuntimeCapability,type ResearchRuntimeStatus} from '../../shared/researchRuntime';
import type {ApiOperation} from '../../shared/contracts';
import {ServiceError} from './contracts';

type Transport=(operation:ApiOperation,path:string,method?:string,payload?:unknown,signal?:AbortSignal)=>Promise<unknown>;
export interface ResearchRuntimeService {
  capability(signal?:AbortSignal):Promise<ResearchRuntimeCapability>;
  status(taskId:string,signal?:AbortSignal):Promise<ResearchRuntimeStatus>;
  advance(taskId:string,runId:string,signal?:AbortSignal):Promise<ResearchRuntimeStatus>;
}
export function createResearchRuntimeService(transport:Transport):ResearchRuntimeService {
  function bound(raw:unknown,taskId:string,runId?:string) {
    const result=researchRuntimeStatusSchema.parse(raw);
    if(result.taskId!==taskId || (runId && result.runId!==runId))
      throw new ServiceError('INVALID_SERVICE_RESPONSE','研究结果与当前任务不一致，请核对原任务。');
    return result;
  }
  return {
    async capability(signal){
      signal?.throwIfAborted();
      let raw:unknown;
      try{raw=await transport('researchRuntime.capability','/research-execution/capability?source_catalog_version=1','GET',{sourceCatalogVersion:1},signal);}
      catch(error){
        signal?.throwIfAborted();
        if(!(error instanceof ServiceError)||error.status!==422||error.code!=='invalid_request')throw error;
        // Capability negotiation is read-only. Never retry START or an effect.
        raw=await transport('researchRuntime.capability','/research-execution/capability','GET',undefined,signal);
        if(researchRuntimeCapabilitySchema.parse(raw).contractVersion!==1)
          throw new ServiceError('INVALID_SERVICE_RESPONSE','研究能力协商结果不一致。');
      }
      signal?.throwIfAborted();
      return researchRuntimeCapabilitySchema.parse(raw);
    },
    async status(taskId,signal){const payload=researchRuntimeStatusRequestSchema.parse({taskId});
      return bound(await transport('researchRuntime.status',`/research-execution/tasks/${taskId}`,'GET',payload,signal),taskId);},
    async advance(taskId,runId,signal){const payload=researchRuntimeAdvanceRequestSchema.parse({taskId,runId});
      return bound(await transport('researchRuntime.advance',`/research-execution/tasks/${taskId}/advance`,'POST',payload,signal),taskId,runId);},
  };
}
