import type {
  CoverageSnapshot,
  SearchCoverageQuery,
} from "../domain/searchCoverage";
import {parseCoverageSnapshot,searchCoverageQuerySchema} from '../domain/searchCoverage';
import type {ApiOperation} from '../../shared/contracts';
import type {Session} from '../domain/models';

/** Optional, read-only, authenticated coverage API. No fallback to TaskRun.events.
 * The adapter must verify session accountScope before exposing this capability.
 * query.expectedScope is checked against server authentication, never used to select
 * an arbitrary account. Returns one bounded, internally consistent run/window snapshot.
 * It performs no new collection, quota reservation, resumption or charge. */
export interface SearchCoverageService {
  query(
    request: SearchCoverageQuery,
    signal?: AbortSignal,
  ): Promise<CoverageSnapshot>;
}

type Transport=(operation:ApiOperation,path:string,method?:string,payload?:unknown,signal?:AbortSignal)=>Promise<unknown>;
const checkAbort=(signal?:AbortSignal)=>{if(signal?.aborted)throw new DOMException('请求已取消。','AbortError');};
export function createSearchCoverageService(transport:Transport,session:()=>Promise<Session>):SearchCoverageService {
  return {async query(request,signal){
    const input=searchCoverageQuerySchema.parse(request);
    checkAbort(signal);
    const current=await session();
    checkAbort(signal);
    if(!current.authenticated||current.userId!==input.expectedScope.userId||
        current.accountScope?.id!==input.expectedScope.accountScopeId||
        current.accountScope?.version!==input.expectedScope.scopeVersion)
      throw new Error('当前账户与搜索覆盖范围不一致。');
    const raw=await transport('coverage.query','/search-coverage','POST',input,signal);
    checkAbort(signal);
    return parseCoverageSnapshot(raw,input);
  }};
}
