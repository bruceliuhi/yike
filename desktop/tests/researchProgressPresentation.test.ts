import {expect,it} from 'vitest';
import {researchProgressPresentation} from '../src/renderer/domain/researchProgressPresentation';
import {RESEARCH_RUNTIME_SOURCE_LABEL,RESEARCH_RUNTIME_SOURCE_SCOPE,researchRuntimeStatusSchema,type ResearchRuntimeStatus} from '../src/shared/researchRuntime';
import {dynamicStatus} from './fixtures/dynamicResearch';

const counts={issued:0,pending:0,succeeded:0,failed:0,unknown:0};
function value(overrides:Partial<ResearchRuntimeStatus>={}):ResearchRuntimeStatus {
  return {contractVersion:1,taskId:'11111111-1111-4111-8111-111111111111',runId:'22222222-2222-4222-8222-222222222222',
    phase:'QUEUED',sourceScope:RESEARCH_RUNTIME_SOURCE_SCOPE,sourceLabel:RESEARCH_RUNTIME_SOURCE_LABEL,
    acceptedOriginals:null,analyzedOriginals:0,skippedOriginals:0,candidateIds:[],canAdvance:true,stopCode:null,
    newActionsBlocked:false,effectsPending:false,usage:{sourceReads:{...counts},modelCalls:{...counts},actualSoubei:null,settlementState:'PENDING'},
    ...overrides};
}

it.each([
  ['QUEUED','已准备好，等待开始'],['RUNNING','研究进行中'],['STOPPED','研究已暂停'],
  ['CANCELED','已停止新增研究'],['COMPLETED','本轮研究已完成'],
] as const)('maps %s to its customer title',(phase,title)=>{
  expect(researchProgressPresentation(value({phase})).title).toBe(title);
});

it('distinguishes zero, positive, and unconfirmed completed originals',()=>{
  expect(researchProgressPresentation(value({phase:'COMPLETED',acceptedOriginals:0}))).toMatchObject({
    explanation:'本轮未找到可分析的原文。',
  });
  expect(researchProgressPresentation(value({phase:'COMPLETED',acceptedOriginals:2})).nextStep).toContain('查看原文与分析');
  const unknown=researchProgressPresentation(value({phase:'COMPLETED',acceptedOriginals:null}));
  expect(unknown.explanation).toContain('原文数量尚未确认');
  expect(unknown.nextStep).toContain('刷新进度');
});

it('distinguishes pages read from selected candidates without declaring all pages background',()=>{
  const input=value({contractVersion:4,phase:'COMPLETED',acceptedOriginals:0,
    discovery:{searches:{...counts,issued:1,succeeded:1},reads:{...counts,issued:3,succeeded:3},unpublishedOriginals:3}});
  const shown=researchProgressPresentation(input);
  expect(shown.explanation).toBe('已读取 3 篇公开页面，暂未选出合适线索。');
  expect(shown.explanation).not.toContain('全部为背景');
  expect(researchProgressPresentation({...input,discovery:{...input.discovery!,reads:{...counts}}}).explanation)
    .toBe('本轮未找到可分析的原文。');
});

it.each([
  ['effect_unknown','研究结果仍待确认。'],['assessment_unknown','研究结果仍待确认。'],
  ['effect_failed','本轮读取或分析未完成。'],['assessment_failed','本轮读取或分析未完成。'],
  ['resource_limit_exceeded','本轮已达到确认的研究用量上限。'],['task_unavailable','当前任务暂时不能继续。'],
  ['capability_unavailable','当前服务暂不支持这项研究。'],['resource_unavailable','研究服务暂时不可用。'],
  ['lease_conflict','任务状态已变化，请刷新进度。'],['future_code','研究已停止，请刷新进度。'],
  ['constructor','研究已停止，请刷新进度。'],['toString','研究已停止，请刷新进度。'],
  ['__proto__','研究已停止，请刷新进度。'],
  ['research_selection_invalid','部分原文尚未完成分析。'],
  ['broker_stop_unknown','任务是否已停止仍待确认，请刷新进度。'],
  ['broker_stream_unknown','部分研究结果仍待确认。'],
] as const)('maps stop code %s without exposing the code',(stopCode,explanation)=>{
  const shown=researchProgressPresentation(value({phase:'STOPPED',stopCode,newActionsBlocked:true,canAdvance:false}));
  expect(shown.explanation).toBe(explanation);
  expect(`${shown.title}${shown.explanation}${shown.nextStep}${shown.warning??''}`).not.toContain(stopCode);
});

it('keeps pending and failure risks visible even for terminal success or cancel',()=>{
  const completed=researchProgressPresentation(value({phase:'COMPLETED',effectsPending:true,acceptedOriginals:1}));
  expect(completed.warning).toContain('部分结果仍待确认。');
  const canceled=researchProgressPresentation(value({phase:'CANCELED',usage:{...value().usage,modelCalls:{...counts,failed:1}}}));
  expect(canceled.warning).toBe('部分内容未能完成分析，可查看已有结果。');
  expect(canceled.nextStep).not.toMatch(/重启|重试|继续研究/);
});

it('combines failed and uncertain results in one short customer warning without losing either',()=>{
  const shown=researchProgressPresentation(value({phase:'STOPPED',effectsPending:true,
    usage:{...value().usage,modelCalls:{...counts,issued:1,failed:1}}}));
  expect(shown.warning).toBe('部分内容未完成，另有结果待确认。');
  expect(shown.nextStep).toBe('请先刷新进度，确认结果后再继续。');
});

it('shows normal background work as progress, not an unknown-result warning',()=>{
  const input=researchRuntimeStatusSchema.parse({...dynamicStatus(),phase:'RUNNING',effectsPending:true,newActionsBlocked:true,canAdvance:false,
    usage:{...value().usage,modelCalls:{...counts,issued:1,pending:1},
      resourceCloseout:{state:'DRAINING',overduePermits:0,asOf:'2026-09-13T07:30:00Z'}}});
  expect(researchProgressPresentation(input)).toMatchObject({warning:null,nextStep:'正在研究，请稍候。'});
  for(const risk of [
    {...input,stopCode:'effect_unknown'},
    {...input,usage:{...input.usage,modelCalls:{...counts,issued:1,unknown:1}}},
    {...input,usage:{...input.usage,resourceCloseout:{...input.usage.resourceCloseout!,state:'UNCERTAIN' as const}}},
    {...input,usage:{...input.usage,resourceCloseout:{...input.usage.resourceCloseout!,overduePermits:1}}},
  ])expect(researchProgressPresentation(risk).warning).toContain('部分结果仍待确认');
});

it('detects source and closeout risk without mutating its input',()=>{
  const input=value({sourceProgress:[{sourceId:'v2ex-qna-v1',phase:'UNKNOWN',acceptedOriginals:null,recordLimit:5}],
    usage:{...value().usage,resourceCloseout:{state:'DRAINING',overduePermits:0,asOf:'2026-09-11T14:00:00Z'}}});
  const before=structuredClone(input);
  expect(researchProgressPresentation(input).warning).toContain('部分结果仍待确认');
  expect(input).toEqual(before);
});

it('uses natural cautious language while a running original count is unconfirmed',()=>{
  const shown=researchProgressPresentation(value({phase:'RUNNING',acceptedOriginals:null}));
  expect(shown.explanation).toBe('正在查找并分析相关内容。');
  expect(shown.explanation).not.toContain('当前已确认');
});

it.each(['QUEUED','COMPLETED'] as const)('does not invite new work from %s while effects remain unconfirmed',phase=>{
  const shown=researchProgressPresentation(value({phase,acceptedOriginals:0,effectsPending:true,newActionsBlocked:true}));
  expect(shown.nextStep).toContain('确认结果后再继续');
  expect(shown.nextStep).not.toMatch(/继续研究|新任务|调整策略后再研究/);
});
