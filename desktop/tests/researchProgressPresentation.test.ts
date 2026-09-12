import {expect,it} from 'vitest';
import {researchProgressPresentation} from '../src/renderer/domain/researchProgressPresentation';
import {RESEARCH_RUNTIME_SOURCE_LABEL,RESEARCH_RUNTIME_SOURCE_SCOPE,type ResearchRuntimeStatus} from '../src/shared/researchRuntime';

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
    explanation:'本轮没有取得可供分析的原文，不代表没有市场需求。',
  });
  expect(researchProgressPresentation(value({phase:'COMPLETED',acceptedOriginals:2})).nextStep).toContain('查看原文与分析');
  const unknown=researchProgressPresentation(value({phase:'COMPLETED',acceptedOriginals:null}));
  expect(unknown.explanation).toContain('原文数量尚未确认');
  expect(unknown.nextStep).toContain('查询原研究状态');
});

it.each([
  ['effect_unknown','已有请求的结果尚未核实。'],['assessment_unknown','已有请求的结果尚未核实。'],
  ['effect_failed','本轮读取或分析未完成。'],['assessment_failed','本轮读取或分析未完成。'],
  ['resource_limit_exceeded','本轮已达到确认的研究用量上限。'],['task_unavailable','当前任务暂时不能继续。'],
  ['capability_unavailable','当前服务暂不支持这项研究。'],['resource_unavailable','研究服务暂时不可用。'],
  ['lease_conflict','执行状态发生变化，请查询原任务。'],['future_code','研究已停止，请查看执行明细。'],
] as const)('maps stop code %s without exposing the code',(stopCode,explanation)=>{
  const shown=researchProgressPresentation(value({phase:'STOPPED',stopCode,newActionsBlocked:true,canAdvance:false}));
  expect(shown.explanation).toBe(explanation);
  expect(`${shown.title}${shown.explanation}${shown.nextStep}${shown.warning??''}`).not.toContain(stopCode);
});

it('keeps pending and failure risks visible even for terminal success or cancel',()=>{
  const completed=researchProgressPresentation(value({phase:'COMPLETED',effectsPending:true,acceptedOriginals:1}));
  expect(completed.warning).toContain('尚有请求或执行记录待核实，不会自动重做；停止本页不代表撤回已发请求。');
  const canceled=researchProgressPresentation(value({phase:'CANCELED',usage:{...value().usage,modelCalls:{...counts,failed:1}}}));
  expect(canceled.warning).toContain('读取或分析');
  expect(canceled.nextStep).not.toMatch(/重启|重试|继续研究/);
});

it('detects source and closeout risk without mutating its input',()=>{
  const input=value({sourceProgress:[{sourceId:'v2ex-qna-v1',phase:'UNKNOWN',acceptedOriginals:null,recordLimit:5}],
    usage:{...value().usage,resourceCloseout:{state:'DRAINING',overduePermits:0,asOf:'2026-09-11T14:00:00Z'}}});
  const before=structuredClone(input);
  expect(researchProgressPresentation(input).warning).toContain('尚有请求或执行记录待核实');
  expect(input).toEqual(before);
});

it('uses natural cautious language while a running original count is unconfirmed',()=>{
  const shown=researchProgressPresentation(value({phase:'RUNNING',acceptedOriginals:null}));
  expect(shown.explanation).toBe('本轮正在逐步处理；入库原文数量尚未确认。');
  expect(shown.explanation).not.toContain('当前已确认');
});

it.each(['QUEUED','COMPLETED'] as const)('does not invite new work from %s while effects remain unconfirmed',phase=>{
  const shown=researchProgressPresentation(value({phase,acceptedOriginals:0,effectsPending:true,newActionsBlocked:true}));
  expect(shown.nextStep).toContain('核实已有请求');
  expect(shown.nextStep).not.toMatch(/继续研究|新任务|调整策略后再研究/);
});
