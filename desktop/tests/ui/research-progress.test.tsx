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
it.each([
  ['V2EX_QNA_INDEX','V2EX问与答 · 单源索引研究（未读评论）'],
  ['V2EX_OUTSOURCING_INDEX','V2EX项目外包 · 单源索引研究（未读作者回复）'],
])('renders the actual %s research scope without upgrading it to comment research',async(sourceScope,sourceLabel)=>{
  status.mockResolvedValue({...queued,contractVersion:2,sourceScope,sourceLabel});
  view();await screen.findByText(sourceLabel);
  expect(screen.queryByText(RESEARCH_RUNTIME_SOURCE_LABEL)).toBeNull();
  expect(advance).not.toHaveBeenCalled();
});
it('shows recorded resources separately from financial settlement',async()=>{
  status.mockResolvedValue({...queued,phase:'COMPLETED',canAdvance:false,newActionsBlocked:true,
    usage:{...queued.usage,resourceCloseout:{state:'RECORDED',overduePermits:0,asOf:'2026-09-11T14:00:00Z'}}});
  view();
  await screen.findByText(/本次查询：资源记录已收齐/);
  expect(screen.getByText(/不代表搜贝已结算或余额已释放/)).toBeTruthy();
  expect(screen.getByText(/来源许可：0/)).toBeTruthy();
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
  await screen.findByText('研究序列已完成');
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
