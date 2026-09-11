import type {ApiOperation} from '../../shared/contracts';
import {opportunityBriefQueryWire} from '../../shared/opportunityBrief';
import {briefQuerySchema,parseOpportunityBrief} from '../domain/opportunityBrief';
import type {Session} from '../domain/models';
import type {OpportunityBriefService} from './opportunityBrief';
type Transport=(operation:ApiOperation,path:string,method?:string,payload?:unknown,signal?:AbortSignal)=>Promise<unknown>;
const checkAbort=(signal?:AbortSignal)=>{if(signal?.aborted)throw new DOMException('请求已取消。','AbortError');};

/** Read retained facts only. Neither the request nor a missing result starts research. */
export function createOpportunityBriefService(transport:Transport,session:()=>Promise<Session>):OpportunityBriefService {
 return {async query(request,signal){
  const input=briefQuerySchema.parse(opportunityBriefQueryWire.parse(request));
  const current=async()=>{
   checkAbort(signal);const user=await session();checkAbort(signal);
   if(!user.authenticated||user.userId!==input.userId||user.accountScope?.id!==input.accountScopeId||user.accountScope.version!==input.scopeVersion)
    throw new Error('简报与当前账户不一致，请重新读取。');
  };
  await current();
  const raw=await transport('opportunityBrief.query','/opportunity-brief/query','POST',input,signal);
  await current();
  return parseOpportunityBrief(raw,input);
 }};
}
