// @vitest-environment jsdom
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {ResearchProgress} from '../../src/renderer/pages/tasks/ResearchProgress';
import type {AppContextValue} from '../../src/renderer/app/context';
import {RESEARCH_RUNTIME_SOURCE_LABEL,RESEARCH_RUNTIME_SOURCE_SCOPE,type ResearchRuntimeStatus} from '../../src/shared/researchRuntime';

let context:AppContextValue;
vi.mock('../../src/renderer/app/context',()=>({useApp:()=>context}));
const taskId='11111111-1111-4111-8111-111111111111',runId='22222222-2222-4222-8222-222222222222';
const counts={issued:0,pending:0,succeeded:0,failed:0,unknown:0};
const queued:ResearchRuntimeStatus={contractVersion:1,taskId,runId,phase:'QUEUED',sourceScope:RESEARCH_RUNTIME_SOURCE_SCOPE,
  sourceLabel:RESEARCH_RUNTIME_SOURCE_LABEL,acceptedOriginals:null,analyzedOriginals:0,skippedOriginals:0,
  candidateIds:[],canAdvance:true,stopCode:null,newActionsBlocked:false,effectsPending:false,
  usage:{sourceReads:counts,modelCalls:counts,actualSoubei:null,settlementState:'PENDING'}};
let status:ReturnType<typeof vi.fn>,advance:ReturnType<typeof vi.fn>;
beforeEach(()=>{
  status=vi.fn().mockResolvedValue(queued);advance=vi.fn();
  context={service:{researchRuntime:{status,advance}},session:{authenticated:true,userId:'user'},navigate:vi.fn()} as unknown as AppContextValue;
});
afterEach(cleanup);
function view(){return render(<ResearchProgress taskId={taskId} runId={runId} taskStatus="PENDING"/>);}
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
  view();await screen.findByRole('table',{name:'逐来源研究进度'});
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
it('shows recorded resources separately from financial settlement inside closed details',async()=>{
  status.mockResolvedValue({...queued,phase:'COMPLETED',canAdvance:false,newActionsBlocked:true,
    usage:{...queued.usage,resourceCloseout:{state:'RECORDED',overduePermits:0,asOf:'2026-09-11T14:00:00Z'}}});
  view();
  const summary=await screen.findByText('执行明细');
  expect(summary.closest('details')?.open).toBe(false);
  await screen.findByText(/本次查询：资源记录已收齐/);
  expect(screen.getByText(/不代表搜贝已结算或余额已释放/)).toBeTruthy();
  expect(screen.getByText(/来源许可：0/).closest('details')).toBe(summary.closest('details'));
  expect(advance).not.toHaveBeenCalled();
});
it('old services do not imply recorded or settled resources',async()=>{
  view();await screen.findByText(/服务尚未提供资源收口状态/);
  expect(screen.queryByText(/本次查询：资源记录已收齐/)).toBeNull();
  expect(advance).not.toHaveBeenCalled();
});
it.each(['OPEN','DRAINING','UNCERTAIN'] as const)('shows %s with explicit permit outcomes',async(state)=>{
  const unresolved=state==='UNCERTAIN',pending=state==='OPEN'?0:1;
  status.mockResolvedValue({...queued,canAdvance:state==='OPEN',newActionsBlocked:state!=='OPEN',effectsPending:pending>0,
    usage:{...queued.usage,sourceReads:{...counts,issued:pending,pending},
      resourceCloseout:{state,overduePermits:unresolved?1:0,asOf:'2026-09-11T14:00:00Z'}}});
  view();await screen.findByText(/本次查询：/);
  expect(screen.getByText(/来源许可：/)).toBeTruthy();
  expect(screen.getAllByText(/待回执/).length).toBeGreaterThan(0);
  if(unresolved)expect(screen.getByText(/超期未核实：1/)).toBeTruthy();
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
  expect(screen.getByText(/不是已确认的商机数量/)).toBeTruthy();
  expect(screen.getByText(/实际搜贝待结算/)).toBeTruthy();
});
it('timeout queries original state once and never repeats an unknown model effect',async()=>{
  const unknown={...queued,phase:'STOPPED',canAdvance:false,newActionsBlocked:true,stopCode:'effect_unknown',
    usage:{...queued.usage,modelCalls:{...counts,issued:1,unknown:1}}};
  status.mockResolvedValueOnce(queued).mockResolvedValueOnce(queued).mockResolvedValue(unknown);
  advance.mockRejectedValue(new Error('connection lost'));
  view();await screen.findByText('V2EX最新主题 · 公开单源研究');
  fireEvent.click(screen.getByRole('button',{name:'继续研究'}));
  await screen.findByText(/本轮推进未确认/);
  expect(advance).toHaveBeenCalledTimes(1);
  expect((screen.getByRole('button',{name:'继续研究'}) as HTMLButtonElement).disabled).toBe(true);
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
it('keeps cautious status and risk outside details while raw unknown code stays inside',async()=>{
  status.mockResolvedValue({...queued,phase:'CANCELED',canAdvance:false,newActionsBlocked:true,stopCode:'future_code',effectsPending:true,
    usage:{...queued.usage,sourceReads:{...counts,issued:1,pending:1},resourceCloseout:{state:'DRAINING',overduePermits:0,asOf:'2026-09-11T14:00:00Z'}}});
  view();
  const title=await screen.findByText('已停止新增研究');
  const summary=screen.getByText('执行明细');
  const details=summary.closest('details');
  expect(details?.open).toBe(false);
  expect(title.closest('details')).toBeNull();
  expect(screen.getByText(/尚有请求或执行记录待核实/).closest('details')).toBeNull();
  expect(screen.getByText(/停止原因：future_code/).closest('details')).toBe(details);
  fireEvent.click(summary);
  expect(details?.open).toBe(true);
  expect(advance).not.toHaveBeenCalled();
});
it('shows an unknown-effect stop reason as a primary action without resending',async()=>{
  status.mockResolvedValue({...queued,phase:'STOPPED',canAdvance:false,newActionsBlocked:true,stopCode:'effect_unknown',effectsPending:true,
    usage:{...queued.usage,modelCalls:{...counts,issued:1,unknown:1}}});
  view();
  const explanation=await screen.findByText('已有请求的结果尚未核实。');
  expect(explanation.closest('details')).toBeNull();
  expect(screen.getByText(/核实已有请求，不要重新发送/).closest('details')).toBeNull();
  expect(advance).not.toHaveBeenCalled();
});
it('shows zero versus unknown completion honestly and preserves candidate navigation',async()=>{
  status.mockResolvedValue({...queued,phase:'COMPLETED',acceptedOriginals:0,canAdvance:false,newActionsBlocked:true});
  view();await screen.findByText('本轮没有取得可供分析的原文，不代表没有市场需求。');
  expect(screen.getByText(/新任务/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'查看原文与分析'}));
  expect(context.navigate).toHaveBeenCalledWith(`/candidates?task=${taskId}`);
  cleanup();
  status.mockResolvedValue({...queued,phase:'COMPLETED',acceptedOriginals:null,canAdvance:false,newActionsBlocked:true});
  view();await screen.findByText(/原文数量尚未确认/);
  expect(screen.getAllByText(/查询原研究状态/).length).toBeGreaterThan(0);
});
it('does not infer unsupported all-web capability from the source label',async()=>{
  view();await screen.findByText(RESEARCH_RUNTIME_SOURCE_LABEL);
  expect(screen.queryByText(/全网|所有网站|后台持续/)).toBeNull();
  expect(advance).not.toHaveBeenCalled();
});
