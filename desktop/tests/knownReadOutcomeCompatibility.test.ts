import {expect,it} from 'vitest';
import {researchRuntimeStatusSchema} from '../src/shared/researchRuntime';
import {researchProgressPresentation} from '../src/renderer/domain/researchProgressPresentation';

// The restricted-PG integration passes its actual runtime status via this
// test-only variable. A standalone run checks the same existing UI contract
// with a labeled synthetic wire sample; neither is real provider evidence.
const sample={
  contractVersion:4,taskId:'11111111-1111-4111-8111-111111111111',
  runId:'22222222-2222-4222-8222-222222222222',phase:'COMPLETED',
  sourceScope:'PUBLIC_WEB_AGENT',sourceLabel:'公开网页自主研究',executionMode:'SERVER_BACKGROUND',
  acceptedOriginals:1,analyzedOriginals:1,skippedOriginals:0,
  candidateIds:['33333333-3333-4333-8333-333333333333'],
  canAdvance:false,stopCode:null,newActionsBlocked:true,effectsPending:false,
  usage:{sourceReads:{issued:3,pending:0,succeeded:2,failed:1,unknown:0},
    modelCalls:{issued:1,pending:0,succeeded:1,failed:0,unknown:0},
    actualSoubei:null,settlementState:'PENDING',
    resourceCloseout:{state:'RECORDED',overduePermits:0,asOf:'2026-09-13T00:00:00Z'}},
  discovery:{searches:{issued:1,pending:0,succeeded:1,failed:0,unknown:0},
    reads:{issued:2,pending:0,succeeded:1,failed:1,unknown:0},unpublishedOriginals:0},
};

it('accepts completed research with a known failed read without hiding the gap or inviting restart',()=>{
  const incoming=process.env.YIKE_KNOWN_READ_TEST_STATUS;
  const status=researchRuntimeStatusSchema.parse(incoming?JSON.parse(incoming):sample);
  expect(status.phase).toBe('COMPLETED');
  expect(status.discovery!.reads).toEqual({issued:2,pending:0,succeeded:1,failed:1,unknown:0});
  expect(status.acceptedOriginals).toBe(1);
  expect(status.analyzedOriginals).toBe(1);
  expect(status.usage.resourceCloseout!.state).toBe('RECORDED');
  const shown=researchProgressPresentation(status);
  expect(shown.title).toBe('本轮研究已完成');
  expect(shown.warning).toBe('部分内容未能完成分析，可查看已有结果。');
  expect(shown.explanation).toContain('核对来源和购买意向');
  expect(shown.nextStep).toContain('逐条复核');
  expect(shown.nextStep).not.toMatch(/重新发送|重试|新建任务/);
  // A failed read must never be smuggled into original counts.
  expect(researchRuntimeStatusSchema.safeParse({...status,acceptedOriginals:2}).success).toBe(false);
});
