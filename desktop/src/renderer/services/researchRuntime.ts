import {researchRuntimeCapabilitySchema,researchRuntimeStatusSchema,researchRuntimeStatusRequestSchema,
  researchRuntimeAdvanceRequestSchema,researchRuntimeReadsRequestSchema,researchRuntimeReadsSchema,
  type ResearchRuntimeCapability,type ResearchRuntimeReads,type ResearchRuntimeStatus} from '../../shared/researchRuntime';
import type {ApiOperation} from '../../shared/contracts';
import {ServiceError} from './contracts';

type Transport=(operation:ApiOperation,path:string,method?:string,payload?:unknown,signal?:AbortSignal)=>Promise<unknown>;
export interface ResearchRuntimeService {
  capability(signal?:AbortSignal):Promise<ResearchRuntimeCapability>;
  status(taskId:string,signal?:AbortSignal):Promise<ResearchRuntimeStatus>;
  advance(taskId:string,runId:string,signal?:AbortSignal):Promise<ResearchRuntimeStatus>;
  reads?(taskId:string,runId:string,after?:number,signal?:AbortSignal):Promise<ResearchRuntimeReads>;
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
      const options=[{query:'?dynamic_research_version=1',payload:{dynamicResearchVersion:1},maxVersion:4},
        {query:'?source_plan_version=1',payload:{sourcePlanVersion:1},maxVersion:3},
        {query:'?source_catalog_version=1',payload:{sourceCatalogVersion:1},maxVersion:2},
        {query:'',payload:undefined,maxVersion:1}] as const;
      for(const [index,option] of options.entries()){
        signal?.throwIfAborted();
        let raw:unknown;
        try{raw=await transport('researchRuntime.capability','/research-execution/capability'+option.query,'GET',option.payload,signal);}
        catch(error){
          signal?.throwIfAborted();
          // Only exact, read-only version negotiation. Never retry START or an effect.
          if(index<options.length-1 && error instanceof ServiceError && error.status===422 && error.code==='invalid_request')continue;
          throw error;
        }
        signal?.throwIfAborted();
        const parsed=researchRuntimeCapabilitySchema.parse(raw);
        if(parsed.contractVersion>option.maxVersion)
          throw new ServiceError('INVALID_SERVICE_RESPONSE','研究能力协商结果不一致。');
        return parsed;
      }
      throw new ServiceError('INVALID_SERVICE_RESPONSE','研究能力协商未完成。');
    },
    async status(taskId,signal){const payload=researchRuntimeStatusRequestSchema.parse({taskId});
      return bound(await transport('researchRuntime.status',`/research-execution/tasks/${taskId}`,'GET',payload,signal),taskId);},
    async advance(taskId,runId,signal){const payload=researchRuntimeAdvanceRequestSchema.parse({taskId,runId});
      return bound(await transport('researchRuntime.advance',`/research-execution/tasks/${taskId}/advance`,'POST',payload,signal),taskId,runId);},
    async reads(taskId,runId,after=0,signal){
      const payload=researchRuntimeReadsRequestSchema.parse({taskId,runId,after,limit:5});
      const result=researchRuntimeReadsSchema.parse(await transport('researchRuntime.reads',
        `/research-execution/tasks/${taskId}/reads?run_id=${runId}&after=${after}&limit=5`,'GET',payload,signal));
      if(result.taskId!==taskId||result.runId!==runId||result.items.some(item=>item.sequence<=after)||
          result.items.length>payload.limit||result.nextAfter!==null&&result.nextAfter<=after)
        throw new ServiceError('INVALID_SERVICE_RESPONSE','研究原文与当前任务不一致，请核对原任务。');
      return result;
    },
  };
}
