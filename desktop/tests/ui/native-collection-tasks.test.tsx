// @vitest-environment jsdom
// Synthetic UI contracts, not real platform collection evidence.
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  act,
} from "@testing-library/react";
import { afterEach, beforeEach, it, expect, vi } from "vitest";
import '@testing-library/jest-dom/vitest';
import { NativeCollectionTasks } from "../../src/renderer/pages/tasks/NativeCollectionTasks";
import {TasksPage} from '../../src/renderer/pages/Tasks';
import {taskDraftOwner} from '../../src/renderer/app/taskDraft';
import {newTaskDraft} from '../../src/renderer/domain/models';
import {defaultResearchSettings} from '../../src/renderer/domain/researchUsage';
import type { AppContextValue } from "../../src/renderer/app/context";
import { parseRoute } from "../../src/renderer/domain/routes";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import {coverageFixture} from './r4-search-coverage-fixtures';
let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
const id = "11111111-1111-4111-8111-111111111111",
  other = "22222222-2222-4222-8222-222222222222";
const item = {
  task_id: id,
  run_id: id,
  device_id: id,
  profile_version_id: id,
  strategy_version_id: id,
  start_request_id: id,
  name: "制造企业需求",
  mode: "once",
  created_at: "2026-09-11T01:00:00Z",
  deadline_at: "2026-09-11T01:10:00Z",
  status: "RUNNING",
  max_records: 20,
  records_used: 2,
  stop_confirmed: false,
  platform_runs: [
    {
      platform_run_id: id,
      platform: "BILIBILI",
      status: "RUNNING",
      execution_generation: 1,
      records_used: 2,
    },
  ],
};
beforeEach(() => {
  clearLocalDrafts();
  sessionStorage.clear();
  localStorage.clear();
  context = {
    session: {
      authenticated: true,
      userId: "user",
      accountScope: { id, version: 1 },
    },
    route: parseRoute("#/collection"),
    navigate: vi.fn(),
    service: {
      taskFeed: {
        list: vi
          .fn()
          .mockResolvedValue({
            schema_version: "execution-task-feed-v1",
            items: [item],
            next_cursor: "next",
          }),
        get: vi.fn().mockResolvedValue(item),
      },
      deviceIdentity: {
        getStatus: vi
          .fn()
          .mockResolvedValue({
            state: "READY",
            deviceId: id,
            credentialVersion: 1,
          }),
      },
      execution: {
        execute: vi.fn(async (c: any) =>
          c.action === "LIST"
            ? { state: "LIST", requests: [] }
            : { state: "UNKNOWN", requestId: c.requestId },
        ),
      },
    },
  } as unknown as AppContextValue;
});
afterEach(() => { cleanup(); vi.useRealTimers(); });
it('refreshes running detail without clearing it and stops reading at completion', async () => {
 context.route=parseRoute(`#/collection?task=${id}`);
 render(<NativeCollectionTasks/>);
 await screen.findByText('当前状态：运行中');
 vi.useFakeTimers();
 // Initial timer was scheduled with real time; manual refresh starts the fake-time cycle.
 await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'刷新任务'}));});
 let finish!:(value:any)=>void;
 vi.mocked(context.service.taskFeed!.get).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
 await act(async()=>{await vi.advanceTimersByTimeAsync(3000);});
 expect(screen.getByText('当前状态：运行中')).toBeInTheDocument();
 expect(finish).toBeTypeOf('function');
 await act(async()=>{finish({...item,status:'SUCCEEDED',stop_confirmed:true});});
 expect(screen.getByText('当前状态：已完成')).toBeInTheDocument();
 const reads=vi.mocked(context.service.taskFeed!.get).mock.calls.length;
 await act(async()=>{await vi.advanceTimersByTimeAsync(9000);});
 expect(context.service.taskFeed!.get).toHaveBeenCalledTimes(reads);
 expect(vi.mocked(context.service.execution!.execute).mock.calls.every(([command])=>command.action==='LIST')).toBe(true);
});
it('keeps the last observation with a visible warning on failed refresh and allows manual refresh', async()=>{
 context.route=parseRoute(`#/collection?task=${id}`);
 render(<NativeCollectionTasks/>); await screen.findByText('当前状态：运行中');
 vi.useFakeTimers();
 await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'刷新任务'}));});
 vi.mocked(context.service.taskFeed!.get).mockRejectedValueOnce(new Error('private transport details'));
 await act(async()=>{await vi.advanceTimersByTimeAsync(3000);});
 expect(screen.getByText('状态更新失败，当前显示上次结果，请刷新任务。')).toBeInTheDocument();
 expect(screen.queryByText('private transport details')).not.toBeInTheDocument();
 const reads=vi.mocked(context.service.taskFeed!.get).mock.calls.length;
 await act(async()=>{await vi.advanceTimersByTimeAsync(9000);});
 expect(context.service.taskFeed!.get).toHaveBeenCalledTimes(reads);
 vi.mocked(context.service.taskFeed!.get).mockResolvedValue({...item,status:'SUCCEEDED'} as never);
 await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'刷新任务'}));});
 expect(screen.getByText('当前状态：已完成')).toBeInTheDocument();
 expect(screen.queryByText('状态更新失败，当前显示上次结果，请刷新任务。')).not.toBeInTheDocument();
});
it('aborts an in-flight automatic read when leaving the task and ignores late results',async()=>{
 context.route=parseRoute(`#/collection?task=${id}`);
 const view=render(<NativeCollectionTasks/>); await screen.findByText('当前状态：运行中');
 vi.useFakeTimers();
 await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'刷新任务'}));});
 let finish!:(value:any)=>void, signal:AbortSignal|undefined;
 vi.mocked(context.service.taskFeed!.get).mockImplementationOnce((_id,s)=>{signal=s;return new Promise(resolve=>{finish=resolve;});});
 await act(async()=>{await vi.advanceTimersByTimeAsync(3000);});
 expect(signal?.aborted).toBe(false);
 context={...context,route:parseRoute('#/collection')};
 await act(async()=>{view.rerender(<NativeCollectionTasks/>);});
 expect(signal?.aborted).toBe(true);
 await act(async()=>{finish({...item,status:'SUCCEEDED'});});
 expect(screen.queryByText('当前状态：已完成')).not.toBeInTheDocument();
});
it.each(['manual', 'account'] as const)('ignores old automatic results after %s refresh',async(kind)=>{
 context.route=parseRoute(`#/collection?task=${id}`);
 const view=render(<NativeCollectionTasks/>); await screen.findByText('当前状态：运行中');
 vi.useFakeTimers();
 await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'刷新任务'}));});
 let finish!:(value:any)=>void, signal:AbortSignal|undefined;
 vi.mocked(context.service.taskFeed!.get).mockImplementationOnce((_id,s)=>{signal=s;return new Promise(resolve=>{finish=resolve;});});
 await act(async()=>{await vi.advanceTimersByTimeAsync(3000);});
 expect(signal?.aborted).toBe(false);
 vi.mocked(context.service.taskFeed!.get).mockResolvedValue({...item,status:'CANCELED'} as never);
 await act(async()=>{
  if(kind==='manual')fireEvent.click(screen.getByRole('button',{name:'刷新任务'}));
  else {
   context={...context,session:{...context.session,accountScope:{id:other,version:2}}};
   view.rerender(<NativeCollectionTasks/>);
  }
 });
 expect(signal?.aborted).toBe(true);
 await act(async()=>{finish({...item,status:'SUCCEEDED'});});
 expect(screen.getByText('当前状态：已取消')).toBeInTheDocument();
 expect(screen.queryByText('当前状态：已完成')).not.toBeInTheDocument();
});
it('rejects an automatic observation from another run without displaying its result',async()=>{
 context.route=parseRoute(`#/collection?task=${id}`);
 render(<NativeCollectionTasks/>); await screen.findByText('当前状态：运行中');
 vi.useFakeTimers();
 await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'刷新任务'}));});
 vi.mocked(context.service.taskFeed!.get).mockResolvedValue({...item,run_id:other,status:'SUCCEEDED'} as never);
 await act(async()=>{await vi.advanceTimersByTimeAsync(3000);});
 expect(screen.getByText('状态更新失败，当前显示上次结果，请刷新任务。')).toBeInTheDocument();
 expect(screen.getByText('当前状态：运行中')).toBeInTheDocument();
});
it('uses research progress rather than the pending collection ledger or coverage for research tasks',async()=>{
 context.route=parseRoute(`#/collection?task=${id}`);
 vi.mocked(context.service.taskFeed!.get).mockResolvedValue({...item,research:true,status:'PENDING',profile_version:3} as never);
 const counts={issued:0,pending:0,succeeded:0,failed:0,unknown:0};
 context.service.researchRuntime={capability:vi.fn(),status:vi.fn().mockResolvedValue({
  contractVersion:4,taskId:id,runId:id,phase:'STOPPED',sourceScope:'PUBLIC_WEB_AGENT',
  sourceLabel:'公开网页自主研究',executionMode:'SERVER_BACKGROUND',acceptedOriginals:0,
  analyzedOriginals:0,skippedOriginals:0,candidateIds:[],canAdvance:false,stopCode:'no_verified_reads',
  newActionsBlocked:true,effectsPending:false,
  discovery:{searches:{...counts,issued:2,succeeded:2},reads:{...counts,issued:1,failed:1},unpublishedOriginals:0},
  usage:{sourceReads:{...counts,issued:3,succeeded:2,failed:1},modelCalls:counts,actualSoubei:null,settlementState:'PENDING'},
 }),advance:vi.fn()};
 context.service.searchCoverage={query:vi.fn()};
 render(<NativeCollectionTasks/>);
 expect(await screen.findByText('研究已暂停')).toBeVisible();
 expect(screen.queryByText(/当前状态：待执行/)).toBeNull();
 expect(screen.queryByRole('region',{name:'搜索覆盖与结果解释'})).toBeNull();
 expect(context.service.searchCoverage.query).not.toHaveBeenCalled();
 expect(screen.getByRole('button',{name:'查看原文与分析'})).toBeVisible();
 expect(screen.getByRole('button',{name:'取消本次采集'})).toBeVisible();
 expect(context.service.researchRuntime!.advance).not.toHaveBeenCalled();
});
it('links research rows to their authoritative progress instead of labeling their upload ledger pending',async()=>{
 vi.mocked(context.service.taskFeed!.list).mockResolvedValue({schema_version:'execution-task-feed-v1',
  items:[{...item,research:true,status:'PENDING'} as never],next_cursor:null});
 render(<NativeCollectionTasks/>);
 fireEvent.click(await screen.findByRole('button',{name:'查看研究进度'}));
 expect(screen.queryByText('待执行')).toBeNull();
 expect(context.navigate).toHaveBeenCalledWith(`/collection?task=${id}`);
});
it('keeps task status and actions up front while hiding server bookkeeping',async()=>{
 context.route=parseRoute(`#/collection?task=${id}`);
 render(<NativeCollectionTasks/>);
 await screen.findByRole('button',{name:'取消本次采集'});
 expect(screen.getByText(/服务端停止登记：/)).not.toBeVisible();
 expect(screen.getByText(/执行期限：/)).not.toBeVisible();
  expect(screen.getByText(/当前状态：运行中/)).toBeVisible();
  expect(screen.getByRole('button',{name:'查看本次发现线索'})).toBeVisible();
  fireEvent.click(screen.getByText('查看运行详情'));
 expect(screen.getByText(/服务端停止登记：/)).toBeVisible();
});
it('keeps real task details before collapsed search details while retaining expandable coverage', async () => {
  context.route = parseRoute(`#/collection?task=${id}`);
  context.service.searchCoverage = { query: vi.fn(async () => coverageFixture()) } as any;
  vi.mocked(context.service.taskFeed!.get).mockResolvedValue({ ...item, profile_version: 1 } as any);
  const { container } = render(<NativeCollectionTasks />);
  await screen.findByRole('button', { name: '查看本次发现线索' });
  const details = screen.getByRole('region', { name: '真实采集详情' });
  const advanced = container.querySelector('details.usage-advanced:last-of-type');
  expect(advanced).not.toBeNull();
  expect(advanced).not.toHaveAttribute('open');
  expect(details.compareDocumentPosition(advanced!) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  expect(screen.getByRole('region', { name: '搜索覆盖与结果解释' })).not.toBeVisible();
  fireEvent.click(screen.getByText('查看搜索详情'));
  expect(screen.getByRole('region', { name: '搜索覆盖与结果解释' })).toBeVisible();
});
it('removes task identity while leaving status and cancellation visible', async()=>{
 context.route=parseRoute(`#/collection?task=${id}`);
 render(<NativeCollectionTasks/>);
 await screen.findByRole('button',{name:'取消本次采集'});
 expect(document.body.textContent).not.toContain(id);
 expect(screen.getByRole('button',{name:'取消本次采集'})).toBeTruthy();
 expect(screen.getByText(/当前状态：运行中/).closest('details')).toBeNull();
});
it.each(['CANCELLING','CANCELED'])('keeps an unconfirmed physical stop visible for %s even with diagnostics closed',async(status)=>{
 context.route=parseRoute(`#/collection?task=${id}`);
 vi.mocked(context.service.taskFeed!.get).mockResolvedValue({...item,status,stop_confirmed:false} as never);
 render(<NativeCollectionTasks/>);
 expect(await screen.findByText('停止结果尚未确认，请刷新当前任务，不要重复启动。')).toBeVisible();
 expect(screen.getByText(/服务端停止登记：/)).not.toBeVisible();
});
it('creates a fresh ordinary draft from the production task-feed route in the current account scope',async()=>{
 const key='yike.ui.draft.v1.task.'+taskDraftOwner(context.session.userId,context.session.accountScope);
 const previous={...newTaskDraft(),research:defaultResearchSettings()};
 sessionStorage.setItem(key,JSON.stringify(previous));
 render(<TasksPage/>);
 fireEvent.click(await screen.findByRole('button',{name:'新建普通采集'}));
 const draft=JSON.parse(sessionStorage.getItem(key)!);
 expect(draft.id).not.toBe(previous.id);expect(draft.research).toBeUndefined();expect(draft.mode).toBe('once');
 expect(context.navigate).toHaveBeenCalledWith('/tasks/new');
 expect(vi.mocked(context.service.execution!.execute).mock.calls.every(([c])=>c.action==='LIST')).toBe(true);
});
it('shows coverage for the real task using its original numeric profile version',async()=>{
 context.route=parseRoute(`#/collection?task=${id}`);
 vi.mocked(context.service.taskFeed!.get).mockResolvedValue({...item,profile_version:3} as any);
 context.service.searchCoverage={query:vi.fn(async query=>{
  const snapshot=coverageFixture(query);
  return {...snapshot,screening:'UNKNOWN' as const,units:[{...snapshot.units[0],platform:'bilibili' as const,
   stopReason:'UNKNOWN' as const,explanation:'已上传记录可核对，未检查范围仍保留。'}]};
 })};
 render(<NativeCollectionTasks/>);
 await screen.findByText('已上传记录可核对，未检查范围仍保留。');
 expect(context.service.searchCoverage!.query).toHaveBeenCalledWith(expect.objectContaining({
  taskId:id,profileId:id,profileVersion:3,expectedScope:{userId:'user',accountScopeId:id,scopeVersion:1},
 }),expect.any(AbortSignal));
});
function recoverySetup() {
  context.route=parseRoute(`#/collection?task=${id}`);
  const status={state:'STATUS',taskId:id,localState:'INTERRUPTED',serverStatus:'RUNNING',stopConfirmed:false,recordsUsed:2,recoverable:true};
  context.service.foregroundCollection={execute:vi.fn().mockResolvedValue(status)} as any;
  const receipt={schema_version:'execution-runtime-v1',operation:'START',request_id:id,task_id:id,run_id:id,status:'PENDING',stop_confirmed:false,
    platform_runs:[{platform_run_id:id,platform:'BILIBILI',status:'PENDING'}]};
  vi.mocked(context.service.execution!.execute).mockImplementation(async(c:any)=>c.action==='LIST'?{state:'LIST',requests:[]}:{state:'RECORDED',receipt} as any);
  return status;
}
it('recovers only original uploads and explicitly confirms original START continuation',async()=>{
  recoverySetup();render(<NativeCollectionTasks/>);
  await screen.findByRole('button',{name:'查询本机采集状态'});
  fireEvent.click(screen.getByRole('button',{name:'查询本机采集状态'}));
  const recover=await screen.findByRole('button',{name:'核对原上传'});
  fireEvent.click(recover);expect(context.service.foregroundCollection!.execute).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole('button',{name:'确认核对'}));
  await waitFor(()=>expect(context.service.foregroundCollection!.execute).toHaveBeenCalledWith({action:'RECOVER',taskId:id,humanConfirmed:true,retry:true}));
  await waitFor(()=>expect(screen.queryByRole('button',{name:'确认核对'})).toBeNull());
  fireEvent.click(screen.getByRole('button',{name:'继续未执行平台'}));
  expect(context.service.execution!.execute).not.toHaveBeenCalledWith(expect.objectContaining({retry:true}));
  fireEvent.click(screen.getByRole('button',{name:'确认继续'}));
  await waitFor(()=>expect(context.service.execution!.execute).toHaveBeenCalledWith({action:'RECOVER',requestId:id,retry:false}));
  await waitFor(()=>expect(context.service.execution!.execute).toHaveBeenCalledWith({action:'RECOVER',requestId:id,retry:true,humanConfirmed:true}));
});
it('never retries a missing original receipt or after device identity changes',async()=>{
  recoverySetup();render(<NativeCollectionTasks/>);
  await screen.findByRole('button',{name:'查询本机采集状态'});fireEvent.click(screen.getByRole('button',{name:'查询本机采集状态'}));
  fireEvent.click(await screen.findByRole('button',{name:'继续未执行平台'}));
  vi.mocked(context.service.execution!.execute).mockResolvedValue({state:'NOT_FOUND'});
  fireEvent.click(screen.getByRole('button',{name:'确认继续'}));
  await screen.findByText(/原启动回执尚未核实/);
  expect(context.service.execution!.execute).not.toHaveBeenCalledWith(expect.objectContaining({retry:true}));
  vi.mocked(context.service.deviceIdentity!.getStatus).mockResolvedValue({state:'READY',deviceId:other,credentialVersion:1} as any);
  fireEvent.click(screen.getByRole('button',{name:'确认继续'}));
  await screen.findByText(/设备身份已变化/);
  expect(context.service.execution!.execute).not.toHaveBeenCalledWith(expect.objectContaining({retry:true}));
});
it("loads real server rows, paginates without execution and routes to exact task", async () => {
  render(<NativeCollectionTasks />);
  await screen.findByRole("button", { name: "制造企业需求" });
  expect(screen.getByText("2 / 20")).toBeTruthy();
  expect(screen.getByText("B站").closest(".brand-platform-label")).toBeTruthy();
  expect(document.querySelector("tbody .brand-platform-icon img")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "制造企业需求" }));
  expect(context.navigate).toHaveBeenCalledWith(`/collection?task=${id}`);
  vi.mocked(context.service.taskFeed!.list).mockResolvedValue({
    schema_version: "execution-task-feed-v1",
    items: [],
    next_cursor: null,
  });
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  await screen.findByText("本页没有采集任务。");
  expect(context.service.taskFeed!.list).toHaveBeenLastCalledWith(
    { limit: 20, cursor: "next" },
    expect.any(AbortSignal),
  );
  expect(
    vi
      .mocked(context.service.execution!.execute)
      .mock.calls.every(([c]) => c.action === "LIST"),
  ).toBe(true);
});
it("deep link reads its own task; confirmation cancels once and retains unknown for receipt recovery", async () => {
  context.route = parseRoute(`#/collection?task=${id}`);
  render(<NativeCollectionTasks />);
  await screen.findByRole("button", { name: "取消本次采集" });
  fireEvent.click(screen.getByRole('button',{name:'查看本次发现线索'}));
  expect(context.navigate).toHaveBeenCalledWith(`/candidates?task=${id}`);
  await waitFor(() =>
    expect(
      (
        screen.getByRole("button", {
          name: "取消本次采集",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false),
  );
  fireEvent.click(screen.getByRole("button", { name: "取消本次采集" }));
  expect(
    vi
      .mocked(context.service.execution!.execute)
      .mock.calls.every(([c]) => c.action === "LIST"),
  ).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "确认取消" }));
  await screen.findByRole("button", { name: "查询原执行请求" });
  expect(
    vi
      .mocked(context.service.execution!.execute)
      .mock.calls.filter(([c]) => c.action === "CANCEL"),
  ).toHaveLength(1);
  expect(
    (screen.getByRole("button", { name: "取消本次采集" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "查询原执行请求" }));
  await waitFor(() =>
    expect(
      vi
        .mocked(context.service.execution!.execute)
        .mock.calls.some(([c]) => c.action === "RECOVER"),
    ).toBe(true),
  );
  expect(context.service.taskFeed!.get).toHaveBeenCalledWith(
    id,
    expect.any(AbortSignal),
  );
  expect(context.service.taskFeed!.list).not.toHaveBeenCalled();
});
it("keeps other-device tasks read-only and does not claim an error is an empty list", async () => {
  context.route = parseRoute(`#/collection?task=${id}`);
  vi.mocked(context.service.deviceIdentity!.getStatus).mockResolvedValue({
    state: "READY",
    deviceId: other,
    credentialVersion: 1,
  } as any);
  const view = render(<NativeCollectionTasks />);
  await screen.findByText(/请在创建任务的设备/);
  expect(
    (screen.getByRole("button", { name: "取消本次采集" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  context.route = parseRoute("#/collection");
  vi.mocked(context.service.taskFeed!.list).mockRejectedValue(
    new Error("读取失败"),
  );
  view.rerender(<NativeCollectionTasks />);
  await screen.findByText("读取失败");
  expect(screen.queryByText("本页没有采集任务。")).toBeNull();
});
it("drops late detail and confirmation across task navigation", async () => {
  context.route = parseRoute(`#/collection?task=${id}`);
  const view = render(<NativeCollectionTasks />);
  await screen.findByRole("button", { name: "取消本次采集" });
  fireEvent.click(screen.getByRole("button", { name: "取消本次采集" }));
  let resolve!: (v: any) => void;
  vi.mocked(context.service.taskFeed!.get).mockImplementationOnce(
    () => new Promise((r) => (resolve = r)),
  );
  context.route = parseRoute(`#/collection?task=${other}`);
  view.rerender(<NativeCollectionTasks />);
  expect(screen.queryByRole("button", { name: "确认取消" })).toBeNull();
  context.session = { ...context.session, userId: "new-user" };
  vi.mocked(context.service.taskFeed!.get).mockRejectedValue(
    new Error("无权读取"),
  );
  view.rerender(<NativeCollectionTasks />);
  await screen.findByText("无权读取");
  await act(async () =>
    resolve({ ...item, task_id: other, name: "旧用户数据" }),
  );
  expect(screen.queryByText("旧用户数据")).toBeNull();
});
