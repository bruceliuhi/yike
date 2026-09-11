import {expect,it,vi} from 'vitest';
import {createResearchRuntimeService} from '../src/renderer/services/researchRuntime';
import {RESEARCH_RUNTIME_SOURCE_LABEL,RESEARCH_RUNTIME_SOURCE_SCOPE} from '../src/shared/researchRuntime';

const taskId='11111111-1111-4111-8111-111111111111',runId='22222222-2222-4222-8222-222222222222';
const counts={issued:0,pending:0,succeeded:0,failed:0,unknown:0};
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
