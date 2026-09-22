// @vitest-environment jsdom
import {afterEach, beforeEach, expect, it, vi} from "vitest";
import {act, cleanup, fireEvent, render, screen, waitFor, within} from "@testing-library/react";
import {ConnectionsPage} from "../../src/renderer/pages/Connections";
import {ConnectionRegistryTable} from "../../src/renderer/pages/connections/ConnectionRegistryTable";
import {decodeConnectionRegistry} from "../../src/renderer/services/connectionRegistry";
import type {AppContextValue} from "../../src/renderer/app/context";
import type {YikeService} from "../../src/renderer/services/contracts";
import type {PlatformConnection} from "../../src/renderer/domain/models";
import {parseRoute} from "../../src/renderer/domain/routes";
let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({useApp: () => context}));
const records = () => decodeConnectionRegistry({items: ["one", "two"].map((id, index) => ({connection_id: `TEST-connection-${id}`, device_id: `TEST-device-${id}`, account_public_id: "TEST-shared-account", platform: "XIAOHONGSHU", status: index ? "CONNECTED" : "UNVERIFIED", connection_version: index + 1, connected_at: "2026-09-09T00:00:00Z", disconnected_at: null}))});
beforeEach(() => {
  sessionStorage.clear(); localStorage.clear();
  context = {session: {authenticated: true, userId: "TEST-registry", accountScope: {id: "TEST-space", version: 1}}, sessionReady: true, route: parseRoute("#/connections"), navigate: vi.fn(), notify: vi.fn(), refreshSession: vi.fn(), service: {
    connections: vi.fn().mockResolvedValue(records()), connect: vi.fn(), disconnect: vi.fn(), checkConnection: vi.fn(),
  } as unknown as YikeService};
});
afterEach(cleanup);
const details = () => screen.getByRole("button", {name: "查看小红书连接详情：小红书账号2，连接 2"});
it("shows only account, status and times in details without technical identity", async () => {
  render(<ConnectionsPage />);
  await screen.findByText("小红书账号2");
  expect(screen.getByText("小红书账号1")).toBeTruthy();
  expect(screen.queryByText("TEST-shared-account")).toBeNull();
  expect(screen.queryByText(/连接 v2/)).toBeNull();
  expect(screen.queryByText("设备 TEST-device-two")).toBeNull();
  expect(screen.queryByText("已登记设备 · 连接 2")).toBeNull();
  fireEvent.click(details());
  const dialog = within(screen.getByRole("dialog"));
  expect(dialog.queryByText("查看连接技术信息")).toBeNull();
  for (const text of ["TEST-connection-two", "v2", "TEST-device-two", "TEST-shared-account", "可用能力"]) {
    expect(dialog.queryByText(text)).toBeNull();
  }
  expect(dialog.queryByText(/尚无已核验能力|本机账号登录、能力核验与断开操作仍待接通/)).toBeNull();
  for (const text of ["小红书账号2", "已连接", "登记时间", "断开时间"]) {
    expect(dialog.getByText(text).closest("details")).toBeNull();
  }
  expect(context.service.disconnect).not.toHaveBeenCalled();
});
it('shows four account columns without publishing capability details',()=>{
  const rows=records().map(row=>({...row,capabilities:['search','read','monitor','comment','dm','FUTURE_INTERNAL_CODE']}));
  render(<ConnectionRegistryTable rows={rows} loading={false} error="" pendingPlatforms={[]} onOpen={vi.fn()} onDisconnect={vi.fn()} onRefresh={vi.fn()}/>);
  expect(screen.getAllByRole('columnheader').map(cell => cell.textContent)).toEqual(['平台', '当前账号', '连接状态', '操作']);
  expect(screen.queryByText(/FUTURE_INTERNAL_CODE|搜索公开内容|可用能力/)).toBeNull();
  fireEvent.click(details());
  expect(within(screen.getByRole('dialog')).queryByText(/FUTURE_INTERNAL_CODE|搜索公开内容|可用能力/)).toBeNull();
});
it('does not offer a dead login action for a known unavailable platform', () => {
  const onOpen = vi.fn();
  const row: PlatformConnection = {
    platform: 'xhs',
    status: 'UNAVAILABLE',
    capabilities: [],
    reason: '小红书登录服务尚未配置',
  };
  render(<ConnectionRegistryTable rows={[row]} loading={false} error="" pendingPlatforms={[]} onOpen={onOpen} onDisconnect={vi.fn()} onRefresh={vi.fn()} />);
  const action = screen.getByRole('button', {name: '暂不可用'}) as HTMLButtonElement;
  expect(action.disabled).toBe(true);
  expect(action.title).toBe('小红书登录服务尚未配置');
  fireEvent.click(action);
  expect(onOpen).not.toHaveBeenCalled();
});
it("shows both devices for the same account, with exact detail identity and no legacy operation", async () => {
  render(<ConnectionsPage />);
  await screen.findByText("小红书账号2");
  expect(screen.getByText("小红书账号1")).toBeTruthy();
  expect(screen.queryByText("TEST-shared-account")).toBeNull();
  for (const name of ["小红书账号1", "小红书账号2"]) {
    const cells = within(screen.getByText(name).closest("tr")!).getAllByRole("cell");
    expect(cells).toHaveLength(4);
    expect(cells[3].textContent).toBe("查看详情");
  }
  expect(screen.getByText("待核验")).toBeTruthy();
  fireEvent.click(details());
  const dialog = within(screen.getByRole("dialog"));
  expect(dialog.getByText("小红书账号2")).toBeTruthy();
  expect(dialog.getByText("已连接")).toBeTruthy();
  expect(dialog.queryByRole("button", {name: "断开"})).toBeNull();
  expect(context.service.disconnect).not.toHaveBeenCalled();
  expect(context.service.checkConnection).not.toHaveBeenCalled();
});
it("hides stale detail while refreshing and does not turn a read error into no accounts", async () => {
  let reject!: (reason: Error) => void;
  vi.mocked(context.service.connections).mockResolvedValueOnce(records()).mockImplementation(() => new Promise((_, r) => {reject = r;}));
  render(<ConnectionsPage />); await screen.findByText("小红书账号2");
  fireEvent.click(details()); fireEvent.click(screen.getByRole("button", {name: "刷新状态"}));
  await screen.findByText("正在重新读取连接记录…");
  expect(screen.queryByText("TEST-connection-two")).toBeNull();
  await act(async () => reject(new Error("TEST 读取失败")));
  expect(screen.getByText("TEST 读取失败")).toBeTruthy();
  expect(within(screen.getByRole("dialog")).getByText("连接详情读取失败：TEST 读取失败")).toBeTruthy();
  expect(screen.queryByText("未连接")).toBeNull();
});
it("closes account detail on workspace change and ignores the old delayed list", async () => {
  let finish!: (rows: PlatformConnection[]) => void;
  vi.mocked(context.service.connections).mockResolvedValueOnce(records()).mockImplementationOnce(() => new Promise(r => {finish = r;})).mockResolvedValue([]);
  const view = render(<ConnectionsPage />); await screen.findByText("小红书账号2");
  fireEvent.click(details()); fireEvent.click(screen.getByRole("button", {name: "刷新状态"}));
  await waitFor(() => expect(finish).toBeTypeOf("function"));
  context = {...context, session: {...context.session, accountScope: {id: "TEST-space-two", version: 2}}};
  view.rerender(<ConnectionsPage />);
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  await act(async () => finish(records()));
  expect(screen.queryByText("TEST-shared-account")).toBeNull();
  expect(screen.getAllByText("未连接")).toHaveLength(4);
});
