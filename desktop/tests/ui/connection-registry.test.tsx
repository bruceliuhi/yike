// @vitest-environment jsdom
import {afterEach, beforeEach, expect, it, vi} from "vitest";
import {act, cleanup, fireEvent, render, screen, waitFor, within} from "@testing-library/react";
import {ConnectionsPage} from "../../src/renderer/pages/Connections";
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
const details = () => screen.getByRole("button", {name: "查看小红书连接详情：TEST-shared-account，设备TEST-device-two"});
it("folds technical connection identity while preserving account, device, status and capability limits", async () => {
  render(<ConnectionsPage />);
  await screen.findAllByText("TEST-shared-account");
  expect(screen.queryByText(/连接 v2/)).toBeNull();
  expect(screen.getByText("设备 TEST-device-two")).toBeTruthy();
  fireEvent.click(details());
  const dialog = within(screen.getByRole("dialog"));
  const summary = dialog.getByText("查看连接技术信息");
  const technical = summary.closest("details");
  expect(technical).not.toBeNull();
  expect(technical!.open).toBe(false);
  expect(dialog.getByText("TEST-connection-two").closest("details")).toBe(technical);
  expect(dialog.getByText("v2").closest("details")).toBe(technical);
  for (const text of ["TEST-shared-account", "TEST-device-two", "已连接", "尚无已核验能力", "当前可查看服务端连接记录；本机账号登录、能力核验与断开操作仍待接通。"]) {
    expect(dialog.getByText(text).closest("details")).toBeNull();
  }
  fireEvent.click(summary);
  expect(technical!.open).toBe(true);
  expect(within(technical!).getByText("TEST-connection-two")).toBeTruthy();
  expect(context.service.disconnect).not.toHaveBeenCalled();
});
it("shows both devices for the same account, with exact detail identity and no legacy operation", async () => {
  render(<ConnectionsPage />);
  await screen.findAllByText("TEST-shared-account");
  expect(screen.getAllByText("TEST-shared-account")).toHaveLength(2);
  expect(screen.getAllByText("尚无已核验能力")).toHaveLength(2);
  expect(screen.getByText("待核验")).toBeTruthy();
  fireEvent.click(details());
  const dialog = within(screen.getByRole("dialog"));
  expect(dialog.getByText("TEST-connection-two")).toBeTruthy();
  expect(dialog.getByText("TEST-device-two")).toBeTruthy();
  expect(dialog.getByText("v2")).toBeTruthy();
  expect(dialog.queryByRole("button", {name: "断开"})).toBeNull();
  expect(context.service.disconnect).not.toHaveBeenCalled();
  expect(context.service.checkConnection).not.toHaveBeenCalled();
});
it("hides stale detail while refreshing and does not turn a read error into no accounts", async () => {
  let reject!: (reason: Error) => void;
  vi.mocked(context.service.connections).mockResolvedValueOnce(records()).mockImplementation(() => new Promise((_, r) => {reject = r;}));
  render(<ConnectionsPage />); await screen.findAllByText("TEST-shared-account");
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
  const view = render(<ConnectionsPage />); await screen.findAllByText("TEST-shared-account");
  fireEvent.click(details()); fireEvent.click(screen.getByRole("button", {name: "刷新状态"}));
  await waitFor(() => expect(finish).toBeTypeOf("function"));
  context = {...context, session: {...context.session, accountScope: {id: "TEST-space-two", version: 2}}};
  view.rerender(<ConnectionsPage />);
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  await act(async () => finish(records()));
  expect(screen.queryByText("TEST-shared-account")).toBeNull();
  expect(screen.getAllByText("未连接")).toHaveLength(4);
});
