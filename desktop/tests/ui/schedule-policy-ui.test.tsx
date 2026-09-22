// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TaskWizardPage } from "../../src/renderer/pages/TaskWizard";
import { EMPTY_PROFILE, newTaskDraft, type TaskDraft } from "../../src/renderer/domain/models";
import { makeTerm, taskFingerprint } from "../../src/renderer/domain/task";
import { parseRoute } from "../../src/renderer/domain/routes";
import type { AppContextValue } from "../../src/renderer/app/context";
import type { YikeService } from "../../src/renderer/services/contracts";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import type { TaskStartBinding } from "../../src/renderer/domain/taskOperations";
let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
const info = {version: "0.2.0", platform: "test", serviceConfigured: true, deviceReady: true};
let key: string;
const currentDraft = (): TaskDraft => JSON.parse(sessionStorage.getItem(key)!);
function seed(legacy = false) {
  // Exercise the legacy schedule adapter, not the separately gated native public reader.
  const draft = {...newTaskDraft("monitor"), name: "TEST 日程", profileId: "TEST-profile", profileVersion: 1, terms: [makeTerm("TEST 需求")], platforms: ["xhs"] as TaskDraft["platforms"], accounts: {xhs: "TEST-account"}, savedAt: "2026-09-09T00:00:00Z"};
  draft.schedule = {...draft.schedule, kind: "interval", start: "22:00", end: "02:00", timezone: "America/New_York"};
  if (legacy) delete draft.schedule.policyVersion;
  sessionStorage.setItem(key, JSON.stringify(draft)); return draft;
}
function follow(view: ReturnType<typeof render>) {
  const calls = vi.mocked(context.navigate).mock.calls;
  context = {...context, route: parseRoute("#" + calls.at(-1)![0])};
  view.rerender(<TaskWizardPage />);
}
const startButton = () => screen.getByRole("button", {name: "确认并启动"}) as HTMLButtonElement;
async function checkConfirmation() {
  await screen.findByText("TEST 服务");
  fireEvent.click(screen.getByRole("checkbox", {name: /我已核对以上业务画像、搜索条件、账号与运行设置/}));
}
beforeEach(() => {
  cleanup(); clearLocalDrafts(); sessionStorage.clear(); localStorage.clear();
  // A cleared key stays tombstoned for this runtime. Each case is a fresh identity.
  const userId = "TEST-schedule-" + crypto.randomUUID();
  key = "yike.ui.draft.v1.task." + userId;
  context = {
    service: {
      profiles: vi.fn().mockResolvedValue([{id: "TEST-profile", version: 1, status: "CONFIRMED", description: "TEST", fields: {...EMPTY_PROFILE, service: "TEST 服务"}}]),
      connections: vi.fn().mockResolvedValue([{platform: "xhs", accountId: "TEST-account", status: "CONNECTED", capabilities: ["search", "read", "monitor"]}]),
      info: vi.fn().mockResolvedValue(info), suggest: vi.fn().mockRejectedValue(new Error("TEST 未接通")),
      startTask: vi.fn(async (draft: TaskDraft) => ({id: "TEST-created", name: draft.name, mode: draft.mode, platforms: draft.platforms, status: "PENDING"})),
    } as unknown as YikeService,
    session: {authenticated: true, userId}, sessionReady: true,
    route: parseRoute("#/tasks/new?mode=monitor"), navigate: vi.fn(), notify: vi.fn(), refreshSession: vi.fn(),
  };
});
afterEach(cleanup);
it("keeps overnight rules through save, step navigation and final confirmation", async () => {
  seed(); const view = render(<TaskWizardPage />);
  await screen.findByRole("textbox", {name: "任务名称"});
  expect(screen.getByText(/任务窗口：22:00–次日 02:00/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", {name: "保存草稿"}));
  expect(currentDraft().schedule.policyVersion).toBe(1);
  fireEvent.click(screen.getByRole("button", {name: "下一步：连接平台"})); follow(view);
  fireEvent.click(screen.getByRole("button", {name: "下一步：确认任务"})); follow(view);
  expect(screen.getByText("22:00–次日 02:00（含开始，不含结束）")).toBeTruthy();
  expect(screen.getByText(/离线错过的计划不补跑/)).toBeTruthy();
  expect(screen.getByText(/当前页面不代表已经按规则运行/)).toBeTruthy();
  await checkConfirmation(); expect(startButton().disabled).toBe(true);
  expect(context.service.startTask).not.toHaveBeenCalled();
});
it("blocks equal start/end before advancing and preserves the input", async () => {
  seed(); render(<TaskWizardPage />);
  fireEvent.change(await screen.findByLabelText("执行窗口结束"), {target: {value: "22:00"}});
  fireEvent.click(screen.getByRole("button", {name: "下一步：连接平台"}));
  expect(screen.getByText(/执行窗口开始与结束不能相同/)).toBeTruthy();
  expect(context.navigate).not.toHaveBeenCalled(); expect(currentDraft().schedule.end).toBe("22:00");
});
it("leaves old schedule hashes unchanged on entry and adopts only after the explicit action", async () => {
  const original = seed(true); const before = taskFingerprint(original); render(<TaskWizardPage />);
  await screen.findByRole("button", {name: "采用当前日程规则"});
  expect(taskFingerprint(currentDraft())).toBe(before);
  expect(screen.getByText(/历史日程未声明/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", {name: "采用当前日程规则"}));
  expect(currentDraft().schedule.policyVersion).toBe(1);
  expect(currentDraft().terms).toEqual(original.terms);
  expect(taskFingerprint(currentDraft())).not.toBe(before);
});
it("preserves the old unversioned monitor adapter path without claiming v1", async () => {
  seed(true); context.route = parseRoute("#/tasks/new?mode=monitor&step=confirm");
  render(<TaskWizardPage />); await checkConfirmation();
  await waitFor(() => expect(startButton().disabled).toBe(false)); fireEvent.click(startButton());
  await waitFor(() => expect(context.service.startTask).toHaveBeenCalledOnce());
  expect(vi.mocked(context.service.startTask).mock.calls[0][0].schedule.policyVersion).toBeUndefined();
});
it("dispatches v1 only through a declared adapter and keeps its exact schedule", async () => {
  seed(); context.route = parseRoute("#/tasks/new?mode=monitor&step=confirm");
  const start = vi.fn(async (_draft: TaskDraft, binding: TaskStartBinding) => ({...binding, status: "REJECTED" as const, confirmedNotStarted: true as const, message: "TEST 明确未执行"}));
  context.service.taskOperations = {scheduleContractVersion: 1, start} as unknown as YikeService["taskOperations"];
  render(<TaskWizardPage />); await checkConfirmation();
  await waitFor(() => expect(startButton().disabled).toBe(false)); fireEvent.click(startButton());
  await waitFor(() => expect(start).toHaveBeenCalledOnce());
  expect(start.mock.calls[0][0].schedule).toMatchObject({policyVersion: 1, start: "22:00", end: "02:00"});
  expect(context.service.startTask).not.toHaveBeenCalled(); await screen.findByText("TEST 明确未执行");
});
it("rechecks support after delayed preflight before writing a pending start or dispatching", async () => {
  seed(); context.route = parseRoute("#/tasks/new?mode=monitor&step=confirm");
  const start = vi.fn(); context.service.taskOperations = {scheduleContractVersion: 1, start} as unknown as YikeService["taskOperations"];
  let resolve!: (value: typeof info) => void;
  vi.mocked(context.service.info).mockResolvedValueOnce(info).mockImplementationOnce(() => new Promise(r => {resolve = r;}));
  render(<TaskWizardPage />); await checkConfirmation();
  await waitFor(() => expect(startButton().disabled).toBe(false)); fireEvent.click(startButton());
  await waitFor(() => expect(resolve).toBeTypeOf("function"));
  delete context.service.taskOperations!.scheduleContractVersion;
  await act(async () => resolve(info));
  await waitFor(() => expect(screen.getAllByText(/执行服务尚未支持当前日程规则/).length).toBeGreaterThan(0));
  expect(start).not.toHaveBeenCalled(); expect(localStorage.length).toBe(0);
});
