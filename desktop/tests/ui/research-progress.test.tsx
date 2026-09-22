// @vitest-environment jsdom
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import '@testing-library/jest-dom/vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {ResearchProgress} from '../../src/renderer/pages/tasks/ResearchProgress';
import {ResearchReadEvidence} from '../../src/renderer/pages/tasks/ResearchReadEvidence';
import type {AppContextValue} from '../../src/renderer/app/context';
import {RESEARCH_RUNTIME_SOURCE_LABEL,RESEARCH_RUNTIME_SOURCE_SCOPE,type ResearchRuntimeStatus} from '../../src/shared/researchRuntime';
import type {ResearchRuntimeService} from '../../src/renderer/services/researchRuntime';

let context:AppContextValue;
vi.mock('../../src/renderer/app/context',()=>({useApp:()=>context}));
const taskId='11111111-1111-4111-8111-111111111111',runId='22222222-2222-4222-8222-222222222222';
const counts={issued:0,pending:0,succeeded:0,failed:0,unknown:0};
const queued:ResearchRuntimeStatus={contractVersion:1,taskId,runId,phase:'QUEUED',sourceScope:RESEARCH_RUNTIME_SOURCE_SCOPE,
  sourceLabel:RESEARCH_RUNTIME_SOURCE_LABEL,acceptedOriginals:null,analyzedOriginals:0,skippedOriginals:0,
  candidateIds:[],canAdvance:true,stopCode:null,newActionsBlocked:false,effectsPending:false,
  usage:{sourceReads:counts,modelCalls:counts,actualSoubei:null,settlementState:'PENDING'}};
let status:ReturnType<typeof vi.fn>,advance:ReturnType<typeof vi.fn>,reads:ReturnType<typeof vi.fn>;
beforeEach(()=>{
  status=vi.fn().mockResolvedValue(queued);advance=vi.fn();reads=vi.fn();
  context={service:{researchRuntime:{status,advance}},session:{authenticated:true,userId:'user'},navigate:vi.fn()} as unknown as AppContextValue;
});
afterEach(cleanup);
function view(){return render(<ResearchProgress taskId={taskId} runId={runId} taskStatus="PENDING"/>);}
function readMethod(){return reads as unknown as NonNullable<ResearchRuntimeService['reads']>;}
it('gives one short warning and a safe refresh action instead of internal lifecycle explanations',async()=>{
  status.mockResolvedValue({...queued,phase:'STOPPED',canAdvance:false,newActionsBlocked:true,effectsPending:true,
    usage:{...queued.usage,sourceReads:{...counts,issued:1,failed:1},modelCalls:{...counts,issued:1,unknown:1}}});
  view();
  expect(await screen.findByText('部分内容未完成，另有结果待确认。')).toBeVisible();
  expect(screen.queryByText(/尚有请求或执行记录|失败不代表没有结果|停止本页不代表|离开页面/)).toBeNull();
  expect(screen.getByRole('button',{name:'刷新进度'})).toBeEnabled();
  expect(screen.getByRole('button',{name:'继续研究'})).toBeDisabled();
  expect(advance).not.toHaveBeenCalled();
});
it('explains a finished search with no verified original without claiming no market demand',async()=>{
 status.mockResolvedValue({...queued,phase:'STOPPED',stopCode:'no_verified_reads',canAdvance:false,newActionsBlocked:true});
 view();
 expect(await screen.findByText('本轮未找到可核对的原文。')).toBeVisible();
 expect(screen.getByText('可在新任务中调整搜索词或来源后再试。')).toBeVisible();
 expect(screen.getByRole('button',{name:'继续研究'})).toBeDisabled();
 expect(advance).not.toHaveBeenCalled();
});
it('puts execution counts behind diagnostics while keeping results, usage and safe actions visible',async()=>{
  view();
  await screen.findByText(/入库原文：/);
  expect(screen.getByText(/入库原文：/)).not.toBeVisible();
  expect(screen.getByText(/实际搜贝用量待结算/)).toBeVisible();
  expect(screen.getByRole('button',{name:'查看原文与分析'})).toBeVisible();
  expect(screen.getByRole('button',{name:'继续研究'})).toBeVisible();
  fireEvent.click(screen.getByText('查看处理明细'));
  expect(screen.getByText(/入库原文：/)).toBeVisible();
  expect(advance).not.toHaveBeenCalled();
});
it('renders each planned source receipt and continues past the first empty source',async()=>{
  const sourceProgress=[{sourceId:'v2ex-qna-v1',phase:'NOT_STARTED',acceptedOriginals:null,recordLimit:5},
    {sourceId:'v2ex-outsourcing-authors-v1',phase:'NOT_STARTED',acceptedOriginals:null,recordLimit:5}];
  const plan={...queued,contractVersion:3,sourceScope:'V2EX_INDEX_PLAN',sourceLabel:'V2EX多板块 · 有界来源计划',sourceProgress};
  const first={...plan,phase:'RUNNING',sourceProgress:[{...sourceProgress[0],phase:'SUCCEEDED',acceptedOriginals:0},sourceProgress[1]],
    usage:{...queued.usage,sourceReads:{...counts,issued:1,succeeded:1}}};
  const done={...first,phase:'COMPLETED',acceptedOriginals:0,canAdvance:false,newActionsBlocked:true,
    sourceProgress:first.sourceProgress.map(source=>({...source,phase:'SUCCEEDED',acceptedOriginals:0})),
    usage:{...queued.usage,sourceReads:{...counts,issued:2,succeeded:2}}};
  status.mockResolvedValue(plan);
  let release!:(value:unknown)=>void;
  advance.mockResolvedValueOnce(first).mockImplementationOnce(()=>new Promise(resolve=>{release=resolve;}));
  view();await screen.findByText('查看处理明细');
  fireEvent.click(screen.getByText('查看处理明细'));
  await screen.findByRole('table',{name:'逐来源研究进度'});
  fireEvent.click(screen.getByRole('button',{name:'继续研究'}));
  await waitFor(()=>expect(advance).toHaveBeenCalledTimes(2));
  expect(screen.getByText(/入库原文：尚未确认/)).toBeTruthy();
  expect(screen.queryByText('研究序列已完成')).toBeNull();
  release(done);await screen.findByText('本轮研究已完成');
  expect(advance).toHaveBeenCalledTimes(2);
});
it.each([
  ['V2EX_QNA_INDEX','V2EX问与答 · 单源索引研究（未读评论）'],
  ['V2EX_OUTSOURCING_INDEX','V2EX项目外包 · 单源索引研究（未读作者回复）'],
])('renders the actual %s research scope without upgrading it to comment research',async(sourceScope,sourceLabel)=>{
  status.mockResolvedValue({...queued,contractVersion:2,sourceScope,sourceLabel});
  view();await screen.findByText(sourceLabel);
  expect(screen.queryByText(RESEARCH_RUNTIME_SOURCE_LABEL)).toBeNull();
  expect(advance).not.toHaveBeenCalled();
});
it('removes resource internals without implying financial settlement',async()=>{
  status.mockResolvedValue({...queued,phase:'COMPLETED',canAdvance:false,newActionsBlocked:true,
    usage:{...queued.usage,resourceCloseout:{state:'RECORDED',overduePermits:0,asOf:'2026-09-11T14:00:00Z'}}});
  view();
  await screen.findByText(/实际搜贝用量待结算/);
  expect(screen.queryByText('执行明细')).toBeNull();
  expect(screen.queryByText(/来源许可|模型许可/)).toBeNull();
  expect(advance).not.toHaveBeenCalled();
});
it('old services do not imply recorded or settled resources',async()=>{
  view();await screen.findByText(/实际搜贝用量待结算/);
  expect(screen.queryByText(/本次查询：资源记录已收齐/)).toBeNull();
  expect(advance).not.toHaveBeenCalled();
});
it.each(['OPEN','DRAINING','UNCERTAIN'] as const)('keeps %s guarded without displaying internal permits',async(state)=>{
  const unresolved=state==='UNCERTAIN',pending=state==='OPEN'?0:1;
  status.mockResolvedValue({...queued,canAdvance:state==='OPEN',newActionsBlocked:state!=='OPEN',effectsPending:pending>0,
    usage:{...queued.usage,sourceReads:{...counts,issued:pending,pending},
      resourceCloseout:{state,overduePermits:unresolved?1:0,asOf:'2026-09-11T14:00:00Z'}}});
  view();await screen.findByText(/实际搜贝用量待结算/);
  expect(screen.queryByText(/来源许可：|超期未核实：/)).toBeNull();
  expect((screen.getByRole('button',{name:'继续研究'}) as HTMLButtonElement).disabled).toBe(state!=='OPEN');
  expect(advance).not.toHaveBeenCalled();
});
it('a newer snapshot timestamp alone never triggers repeated advances',async()=>{
  const snapshot={...queued,usage:{...queued.usage,resourceCloseout:{state:'OPEN',overduePermits:0,asOf:'2026-09-11T14:00:00Z'}}};
  status.mockResolvedValue(snapshot);
  advance.mockResolvedValue({...snapshot,usage:{...snapshot.usage,resourceCloseout:{...snapshot.usage.resourceCloseout,asOf:'2026-09-11T14:00:01Z'}}});
  view();await screen.findByText('V2EX最新主题 · 公开单源研究');
  fireEvent.click(screen.getByRole('button',{name:'继续研究'}));
  await screen.findByText(/暂未取得新进度/);
  expect(advance).toHaveBeenCalledTimes(1);
});
it('reads without work until asked, then advances serially to honest completion',async()=>{
  const sourced={...queued,phase:'RUNNING',acceptedOriginals:1,usage:{...queued.usage,sourceReads:{...counts,issued:1,succeeded:1}}};
  const completed={...sourced,phase:'COMPLETED',analyzedOriginals:1,canAdvance:false,newActionsBlocked:true,
    usage:{...sourced.usage,modelCalls:{...counts,issued:1,succeeded:1}}};
  let release!:(value:unknown)=>void;
  advance.mockImplementationOnce(()=>new Promise(resolve=>{release=resolve;})).mockResolvedValueOnce(completed);
  view();await screen.findByText('V2EX最新主题 · 公开单源研究');
  expect(advance).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'继续研究'}));
  await waitFor(()=>expect(advance).toHaveBeenCalledTimes(1));
  expect((screen.getByRole('button',{name:'继续研究'}) as HTMLButtonElement).disabled).toBe(true);
  release(sourced);
  await screen.findByText('本轮研究已完成');
  expect(advance).toHaveBeenCalledTimes(2);
  expect(screen.queryByText(/不是已确认的商机数量/)).toBeNull();
  expect(screen.getByText(/实际搜贝用量待结算/)).toBeTruthy();
});
it('timeout queries original state once and never repeats an unknown model effect',async()=>{
  const unknown={...queued,phase:'STOPPED',canAdvance:false,newActionsBlocked:true,stopCode:'effect_unknown',
    usage:{...queued.usage,modelCalls:{...counts,issued:1,unknown:1}}};
  status.mockResolvedValueOnce(queued).mockResolvedValueOnce(queued).mockResolvedValue(unknown);
  advance.mockRejectedValue(new Error('connection lost'));
  view();await screen.findByText('V2EX最新主题 · 公开单源研究');
  fireEvent.click(screen.getByRole('button',{name:'继续研究'}));
  await screen.findByText(/研究进度暂未确认/);
  expect(advance).toHaveBeenCalledTimes(1);
  expect((screen.getByRole('button',{name:'继续研究'}) as HTMLButtonElement).disabled).toBe(true);
});
it('keeps the last confirmed progress visible when an advance and reconciliation both time out',async()=>{
  status.mockResolvedValueOnce(queued).mockRejectedValue(new Error('connection lost'));
  advance.mockRejectedValue(new Error('advance timeout'));
  view();
  await screen.findByText('已准备好，等待开始');
  fireEvent.click(screen.getByRole('button',{name:'继续研究'}));
  await screen.findByText(/研究进度暂未确认，当前仍显示最近一次已核实状态/);
  expect(screen.getByText('已准备好，等待开始')).toBeVisible();
  expect(screen.getByRole('button',{name:'刷新进度'})).toBeEnabled();
});
it('does not spin if server reports the same progress after an advance',async()=>{
  advance.mockResolvedValue(queued);view();await screen.findByText('V2EX最新主题 · 公开单源研究');
  fireEvent.click(screen.getByRole('button',{name:'继续研究'}));
  await screen.findByText(/暂未取得新进度/);
  expect(advance).toHaveBeenCalledTimes(1);
});
it('leaving the page prevents later completions from advancing again',async()=>{
  let release!:(value:unknown)=>void;advance.mockImplementation(()=>new Promise(resolve=>{release=resolve;}));
  const rendered=view();await screen.findByText('V2EX最新主题 · 公开单源研究');
  fireEvent.click(screen.getByRole('button',{name:'继续研究'}));
  await waitFor(()=>expect(advance).toHaveBeenCalledTimes(1));rendered.unmount();
  release({...queued,phase:'RUNNING',acceptedOriginals:1});
  await Promise.resolve();expect(advance).toHaveBeenCalledTimes(1);
});
it('keeps cautious status and risk while removing raw unknown code',async()=>{
  status.mockResolvedValue({...queued,phase:'CANCELED',canAdvance:false,newActionsBlocked:true,stopCode:'future_code',effectsPending:true,
    usage:{...queued.usage,sourceReads:{...counts,issued:1,pending:1},resourceCloseout:{state:'DRAINING',overduePermits:0,asOf:'2026-09-11T14:00:00Z'}}});
  view();
  const title=await screen.findByText('已停止新增研究');
  expect(screen.queryByText('执行明细')).toBeNull();
  expect(title.closest('details')).toBeNull();
  expect(screen.getByText(/部分结果仍待确认/).closest('details')).toBeNull();
  expect(document.body.textContent).not.toContain('future_code');
  expect(advance).not.toHaveBeenCalled();
});
it('shows an unknown-effect stop reason as a primary action without resending',async()=>{
  status.mockResolvedValue({...queued,phase:'STOPPED',canAdvance:false,newActionsBlocked:true,stopCode:'effect_unknown',effectsPending:true,
    usage:{...queued.usage,modelCalls:{...counts,issued:1,unknown:1}}});
  view();
  const explanation=await screen.findByText('研究结果仍待确认。');
  expect(explanation.closest('details')).toBeNull();
  expect(screen.getByText(/确认结果后再继续/).closest('details')).toBeNull();
  expect(advance).not.toHaveBeenCalled();
});
it('shows zero versus unknown completion honestly and preserves candidate navigation',async()=>{
  status.mockResolvedValue({...queued,phase:'COMPLETED',acceptedOriginals:0,canAdvance:false,newActionsBlocked:true});
  view();await screen.findByText('本轮未找到可分析的原文。');
  expect(screen.getByText(/新任务/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'查看原文与分析'}));
  expect(context.navigate).toHaveBeenCalledWith(`/candidates?task=${taskId}`);
  cleanup();
  status.mockResolvedValue({...queued,phase:'COMPLETED',acceptedOriginals:null,canAdvance:false,newActionsBlocked:true});
  view();await screen.findByText(/原文数量尚未确认/);
  expect(screen.getAllByText(/刷新进度/).length).toBeGreaterThan(0);
});
it('does not infer unsupported all-web capability from the source label',async()=>{
  view();await screen.findByText(RESEARCH_RUNTIME_SOURCE_LABEL);
  expect(screen.queryByText(/全网|所有网站|后台持续/)).toBeNull();
  expect(advance).not.toHaveBeenCalled();
});
it('loads successful READ evidence only after opening the dynamic read-only section',async()=>{
  const dynamic={...queued,contractVersion:4 as const,sourceScope:'PUBLIC_WEB_AGENT' as const,
    sourceLabel:'公开网页自主研究' as const,executionMode:'SERVER_BACKGROUND' as const,
    acceptedOriginals:0,phase:'STOPPED' as const,canAdvance:false,newActionsBlocked:true,stopCode:'research_selection_invalid',
    discovery:{searches:counts,reads:{...counts,issued:1,succeeded:1},unpublishedOriginals:1},
    usage:{...queued.usage,sourceReads:{...counts,issued:1,succeeded:1}}};
  const item={sequence:2,url:'https://example.com/demand',title:'展台需求',text:'原文'.repeat(400),
    observedAt:'2026-09-13T08:00:00Z',contentSha256:'a'.repeat(64)};
  status.mockResolvedValue(dynamic);reads.mockResolvedValue({contractVersion:1,taskId,runId,items:[item],nextAfter:null});
  context={...context,service:{...context.service,researchRuntime:{status,advance,reads},openExternal:vi.fn()}} as unknown as AppContextValue;
  view();const summary=await screen.findByText('已读原文');
  expect(reads).not.toHaveBeenCalled();
  fireEvent.click(summary);
  await screen.findByText('展台需求');
  expect(screen.getByText(item.url)).toBeTruthy();
  expect(reads).toHaveBeenCalledWith(taskId,runId,0,expect.any(AbortSignal));
  expect(screen.getByText(/研究原文，尚非已确认商机/)).toBeTruthy();
  expect(screen.getByText('展开完整原文')).toBeTruthy();
  expect(screen.getByText('原文'.repeat(400)).className).toContain('fixed-evidence-body--collapsed');
  fireEvent.click(screen.getByRole('button',{name:'展开完整原文'}));
  expect(screen.getByText('原文'.repeat(400))).toBeTruthy();
  expect(advance).not.toHaveBeenCalled();
});
it('keeps legacy progress usable when the optional READ evidence method is absent',async()=>{
  const dynamic={...queued,contractVersion:4 as const,sourceScope:'PUBLIC_WEB_AGENT' as const,
    sourceLabel:'公开网页自主研究' as const,executionMode:'SERVER_BACKGROUND' as const,
    acceptedOriginals:0,discovery:{searches:counts,reads:counts,unpublishedOriginals:0}};
  status.mockResolvedValue(dynamic);view();await screen.findByText('公开网页自主研究');
  expect(screen.queryByText('已读原文')).toBeNull();
  expect(screen.getByRole('button',{name:'刷新进度'})).toBeTruthy();
});
it('appends strictly paginated READ evidence without reloading the first page',async()=>{
  const first={sequence:1,url:'https://example.com/one',title:'第一页',text:'第一条原文',
    observedAt:'2026-09-13T08:00:00Z',contentSha256:'a'.repeat(64)};
  const second={...first,sequence:3,url:'https://example.com/two',title:'第二页',text:'第二条原文',contentSha256:'b'.repeat(64)};
  reads.mockResolvedValueOnce({contractVersion:1,taskId,runId,items:[first],nextAfter:1})
    .mockResolvedValueOnce({contractVersion:1,taskId,runId,items:[second],nextAfter:null});
  render(<ResearchReadEvidence taskId={taskId} runId={runId} reads={readMethod()} onOpen={vi.fn()}/>);
  fireEvent.click(screen.getByText('已读原文'));await screen.findByText('第一页');
  fireEvent.click(screen.getByRole('button',{name:'下一页'}));await screen.findByText('第二页');
  expect(reads.mock.calls.map(call=>call.slice(0,3))).toEqual([[taskId,runId,0],[taskId,runId,1]]);
  expect(screen.getAllByRole('article',{name:'研究原文'})).toHaveLength(2);
  expect((screen.getByRole('button',{name:'下一页'}) as HTMLButtonElement).disabled).toBe(true);
});
it('aborts and discards a late READ page when the run changes',async()=>{
  let release!:(value:unknown)=>void;let originalSignal!:AbortSignal;
  reads.mockImplementation((_task,_run,_after,signal)=>{originalSignal=signal!;return new Promise(resolve=>{release=resolve;});});
  const rendered=render(<ResearchReadEvidence taskId={taskId} runId={runId} reads={readMethod()} onOpen={vi.fn()}/>);
  fireEvent.click(screen.getByText('已读原文'));await waitFor(()=>expect(reads).toHaveBeenCalledTimes(1));
  const nextRun='33333333-3333-4333-8333-333333333333';
  rendered.rerender(<ResearchReadEvidence taskId={taskId} runId={nextRun} reads={readMethod()} onOpen={vi.fn()}/>);
  expect(originalSignal.aborted).toBe(true);
  release({contractVersion:1,taskId,runId,items:[{sequence:1,url:'https://example.com/old',title:'旧任务原文',
    text:'不得显示',observedAt:'2026-09-13T08:00:00Z',contentSha256:'a'.repeat(64)}],nextAfter:null});
  await Promise.resolve();expect(screen.queryByText('旧任务原文')).toBeNull();
});
