import {expect,it,vi} from 'vitest';
import {createResearchRuntimeService} from '../src/renderer/services/researchRuntime';
import {RESEARCH_RUNTIME_SOURCE_LABEL,RESEARCH_RUNTIME_SOURCE_SCOPE} from '../src/shared/researchRuntime';
import {ServiceError} from '../src/renderer/services/contracts';

const taskId='11111111-1111-4111-8111-111111111111',runId='22222222-2222-4222-8222-222222222222';
const counts={issued:0,pending:0,succeeded:0,failed:0,unknown:0};
const legacy={contractVersion:1,sourceScope:RESEARCH_RUNTIME_SOURCE_SCOPE,sourceLabel:RESEARCH_RUNTIME_SOURCE_LABEL,
  maxFreshEffectsPerAdvance:1,settlementState:'PENDING'};
it('negotiates dynamic then plan and catalog with bounded precise legacy fallbacks',async()=>{
  const transport=vi.fn().mockRejectedValueOnce(new ServiceError('invalid_request','legacy',422))
    .mockRejectedValueOnce(new ServiceError('invalid_request','legacy',422))
    .mockRejectedValueOnce(new ServiceError('invalid_request','legacy',422)).mockResolvedValueOnce(legacy);
  expect(await createResearchRuntimeService(transport).capability()).toEqual(legacy);
  expect(transport.mock.calls).toEqual([
    ['researchRuntime.capability','/research-execution/capability?dynamic_research_version=1','GET',{dynamicResearchVersion:1},undefined],
    ['researchRuntime.capability','/research-execution/capability?source_plan_version=1','GET',{sourcePlanVersion:1},undefined],
    ['researchRuntime.capability','/research-execution/capability?source_catalog_version=1','GET',{sourceCatalogVersion:1},undefined],
    ['researchRuntime.capability','/research-execution/capability','GET',undefined,undefined],
  ]);
});
it('never falls back on other failures, invalid DTO or abort',async()=>{
  for(const error of [new ServiceError('invalid_request','failure',500),new ServiceError('invalid_session','failure',422),new Error('network')]){
    const transport=vi.fn().mockRejectedValue(error);
    await expect(createResearchRuntimeService(transport).capability()).rejects.toBe(error);
    expect(transport).toHaveBeenCalledTimes(1);
  }
  const invalid=vi.fn().mockResolvedValue({...legacy,sourceIds:[]});
  await expect(createResearchRuntimeService(invalid).capability()).rejects.toThrow();
  expect(invalid).toHaveBeenCalledTimes(1);
  const abort=new AbortController(),transport=vi.fn().mockImplementation(async()=>{
    abort.abort();throw new ServiceError('invalid_request','old',422);
  });
  await expect(createResearchRuntimeService(transport).capability(abort.signal)).rejects.toThrow();
  expect(transport).toHaveBeenCalledTimes(1);
});
const status={contractVersion:1,taskId,runId,phase:'QUEUED',sourceScope:RESEARCH_RUNTIME_SOURCE_SCOPE,
  sourceLabel:RESEARCH_RUNTIME_SOURCE_LABEL,acceptedOriginals:null,analyzedOriginals:0,skippedOriginals:0,
  candidateIds:[],canAdvance:true,stopCode:null,newActionsBlocked:false,effectsPending:false,
  usage:{sourceReads:counts,modelCalls:counts,actualSoubei:null,settlementState:'PENDING'}};
it('uses scoped status/advance routes and rejects a response for another task/run',async()=>{
  const transport=vi.fn().mockResolvedValue(status),service=createResearchRuntimeService(transport);
  expect(await service.status(taskId)).toEqual(status);
  expect(transport).toHaveBeenLastCalledWith('researchRuntime.status',`/research-execution/tasks/${taskId}`,'GET',{taskId},undefined);
  await service.advance(taskId,runId);
  expect(transport).toHaveBeenLastCalledWith('researchRuntime.advance',`/research-execution/tasks/${taskId}/advance`,'POST',{taskId,runId},undefined);
  transport.mockResolvedValue({...status,runId:taskId});
  await expect(service.advance(taskId,runId)).rejects.toThrow();
  transport.mockResolvedValue({...status,taskId:runId});
  await expect(service.status(taskId)).rejects.toThrow();
});
it('never repairs invalid counts or settles unknown usage',async()=>{
  const transport=vi.fn().mockResolvedValue({...status,usage:{...status.usage,actualSoubei:1}});
  await expect(createResearchRuntimeService(transport).status(taskId)).rejects.toThrow();
});
