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
import { NativeCollectionTasks } from "../../src/renderer/pages/tasks/NativeCollectionTasks";
import type { AppContextValue } from "../../src/renderer/app/context";
import { parseRoute } from "../../src/renderer/domain/routes";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
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
afterEach(cleanup);
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
