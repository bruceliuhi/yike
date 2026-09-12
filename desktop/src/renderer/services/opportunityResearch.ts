import type {
  ResearchBinding,
  ResearchCollection,
  ResearchTimeline,
  SimilarResearchPlan,
} from "../domain/opportunityResearch";
import {
  hasResearchScope,
  parseResearchCollection,
  parseResearchTimeline,
  parseSimilarResearch,
} from "../domain/opportunityResearch";
import type { Session } from "../domain/models";
import type {ApiOperation} from '../../shared/contracts';
import {researchTimelineRequestSchema,researchSimilarRequestSchema} from '../../shared/opportunityResearchApi';
import {ServiceError} from './contracts';
/** Optional, authenticated R4 research reads. No production adapter is implied.
 * The server derives tenant identity and verifies profile/source versions.
 * These methods never import, classify, execute research, send, or charge.
 * Similar suggestions are a preview; applying creates only a local draft. */
export interface OpportunityResearchService {
  list(signal?: AbortSignal): Promise<ResearchCollection>;
  timeline(
    binding: ResearchBinding,
    signal?: AbortSignal,
  ): Promise<ResearchTimeline>;
  similar(
    binding: ResearchBinding,
    requestId: string,
    signal?: AbortSignal,
  ): Promise<SimilarResearchPlan>;
}
type Transport=(operation:ApiOperation,path:string,method?:string,payload?:unknown,signal?:AbortSignal)=>Promise<unknown>;
const checkAbort=(signal?:AbortSignal)=>{if(signal?.aborted)throw new DOMException('请求已取消。','AbortError');};
/** Only immutable database reads and a free preview. No model or platform call. */
export function createOpportunityResearchService(transport:Transport,session:()=>Promise<Session>):OpportunityResearchService{
 return {
  async list(signal){
   checkAbort(signal);const current=await session();checkAbort(signal);
   if(!current.authenticated||!current.userId||!hasResearchScope(current.accountScope))throw new Error('当前账户空间尚未核验。');
   const raw=await transport('research.list','/opportunity-research','GET',undefined,signal);checkAbort(signal);
   return parseResearchCollection(raw,current.userId,Date.now(),current.accountScope);
  },
  async timeline(binding,signal){
   const payload=researchTimelineRequestSchema.parse({binding,timelineSchemaVersion:3});checkAbort(signal);
   let raw:unknown;
   try{raw=await transport('research.timeline','/opportunity-research/timeline','POST',payload,signal);}
   catch(error){
    checkAbort(signal);
    if(!(error instanceof ServiceError)||error.status!==422||error.code!=='invalid_request')throw error;
    raw=await transport('research.timeline','/opportunity-research/timeline','POST',{binding},signal);
   }
   checkAbort(signal);
   return parseResearchTimeline(raw,binding);
  },
  async similar(binding,requestId,signal){
   const payload=researchSimilarRequestSchema.parse({binding,requestId});checkAbort(signal);
   const raw=await transport('research.similar','/opportunity-research/similar','POST',payload,signal);checkAbort(signal);
   return parseSimilarResearch(raw,binding,requestId);
  },
 };
}
export async function readResearchRecord(
  service: OpportunityResearchService,
  session: Session,
  id: string,
  signal?: AbortSignal,
) {
  if (!session.authenticated || !session.userId || id === "sample")
    throw new Error("请登录后读取客户研究记录。");
  if (!hasResearchScope(session.accountScope))
    throw new Error("当前账户空间尚未核验，研究服务暂不可用。");
  const snapshot = parseResearchCollection(
    await service.list(signal),
    session.userId,
    Date.now(),
    session.accountScope,
  );
  const row = snapshot.records.find((item) => item.opportunity.id === id);
  if (!row) throw new Error("当前授权研究集合中未找到该记录，请返回列表刷新。");
  return row;
}
