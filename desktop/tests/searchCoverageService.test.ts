import {describe,it,expect,vi} from 'vitest';
import {createSearchCoverageService} from '../src/renderer/services/searchCoverage';
import {validatedOperation} from '../src/main/servicePolicy';
import {coverageFixture,coverageQuery} from './ui/r4-search-coverage-fixtures';

const session=async()=>({authenticated:true,userId:coverageQuery.expectedScope.userId,
 accountScope:{id:coverageQuery.expectedScope.accountScopeId,version:coverageQuery.expectedScope.scopeVersion}});
describe('connected search coverage',()=>{
 it('reads only a fixed query after independent session validation',async()=>{
  const snapshot=coverageFixture(),transport=vi.fn().mockResolvedValue(snapshot);
  expect(await createSearchCoverageService(transport,session).query(coverageQuery)).toEqual(snapshot);
  expect(transport).toHaveBeenCalledWith('coverage.query','/search-coverage','POST',coverageQuery,undefined);
  const route=validatedOperation({operation:'coverage.query',payload:coverageQuery});
  expect(route).toMatchObject({path:'/api/ui/search-coverage',method:'POST',logout:false});
  expect(JSON.parse(route!.body!)).toEqual(coverageQuery);
  expect(validatedOperation({operation:'coverage.query',payload:{...coverageQuery,tenant_id:'other'}})).toBeNull();
 });
 it('refuses unauthenticated or cross-space input before reading',async()=>{
  const transport=vi.fn();
  await expect(createSearchCoverageService(transport,async()=>({authenticated:false})).query(coverageQuery)).rejects.toThrow();
  await expect(createSearchCoverageService(transport,session).query({...coverageQuery,
   expectedScope:{...coverageQuery.expectedScope,accountScopeId:'other'}})).rejects.toThrow();
  expect(transport).not.toHaveBeenCalled();
 });
 it('retains errors and refuses wrong binding or late aborted result',async()=>{
  const transport=vi.fn().mockResolvedValue({...coverageFixture(),runId:'sample'});
  const service=createSearchCoverageService(transport,session);
  await expect(service.query(coverageQuery)).rejects.toThrow();
  transport.mockRejectedValue(new Error('offline'));
  await expect(service.query(coverageQuery)).rejects.toThrow('offline');
  const abort=new AbortController();abort.abort();transport.mockClear();
  await expect(service.query(coverageQuery,abort.signal)).rejects.toThrow();
  expect(transport).not.toHaveBeenCalled();
  const late=new AbortController();transport.mockImplementation(async()=>{late.abort();return coverageFixture();});
  await expect(service.query(coverageQuery,late.signal)).rejects.toThrow();
 });
});
