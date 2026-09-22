// @vitest-environment jsdom
import { StrictMode, type ReactNode } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { AppProvider, useApp } from "../../src/renderer/app/context";
import { TaskWizardPage } from "../../src/renderer/pages/TaskWizard";
import { OutreachPage } from "../../src/renderer/pages/Outreach";
import { ConnectionsPage } from "../../src/renderer/pages/Connections";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { useTaskDraft } from "../../src/renderer/app/taskDraft";
import { operationLedgerKey } from "../../src/renderer/app/operationLedger";
import { createVisualService } from "./service";
import { configureRecovery, type RecoveryScenario } from "./recovery";
import { TEST_USER } from "./fixtures";
import { VISUAL_MANAGEMENT_SCOPE } from "./management";
import { taskDraftOwner } from "../../src/renderer/app/taskDraft";
function Ready({ children }: { children: ReactNode }) {
  return useApp().sessionReady ? children : null;
}
beforeEach(() => {
  clearLocalDrafts();
  localStorage.clear();
  sessionStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
function mount(
  name: RecoveryScenario,
  page: string,
  route: string,
  content: ReactNode,
) {
  history.replaceState(null, "", "#" + route);
  const h = createVisualService();
  const control = configureRecovery(h, name);
  control.seed(sessionStorage, page);
  if (name === "ai-late" || name === "start-unknown") {
    // Each real harness URL loads a fresh document. This test file reuses the
    // module, whose clear tombstones correctly refuse out-of-band reseeding;
    // initialize the next TEST draft via the real setter instead of bypassing it.
    const seeded = JSON.parse(
      sessionStorage.getItem(`yike.ui.draft.v1.task.${TEST_USER}`)!,
    );
    const scopedKey = `yike.ui.draft.v1.task.${taskDraftOwner(TEST_USER, VISUAL_MANAGEMENT_SCOPE)}`;
    sessionStorage.setItem(scopedKey, JSON.stringify(seeded));
    const hook = renderHook(() =>
      useTaskDraft(TEST_USER, seeded.mode, VISUAL_MANAGEMENT_SCOPE),
    );
    act(() => hook.result.current[1](seeded));
    hook.unmount();
  }
  const view = render(
    <StrictMode>
      <AppProvider service={h.service}>
        <Ready>{content}</Ready>
      </AppProvider>
    </StrictMode>,
  );
  return { ...h, control, view };
}
function draft() {
  return JSON.parse(
    sessionStorage.getItem(
      `yike.ui.draft.v1.task.${taskDraftOwner(TEST_USER, VISUAL_MANAGEMENT_SCOPE)}`,
    ) || sessionStorage.getItem(`yike.ui.draft.v1.task.${TEST_USER}`)!,
  );
}
const ledger = (scope: "send-attempts" | "unknown-task-starts") =>
  JSON.parse(
    localStorage.getItem(operationLedgerKey(scope, TEST_USER)) || "{}",
  );
function addTerm(value: string) {
  fireEvent.click(
    within(screen.getByRole("group", { name: "搜索关键词" })).getByRole(
      "button",
      { name: "添加" },
    ),
  );
  const input = screen.getByRole("textbox", { name: "新增搜索关键词" });
  fireEvent.change(input, { target: { value } });
  fireEvent.keyDown(input, { key: "Enter" });
}
it("P06 real page preserves manual terms and schedule until explicitly merging a late TEST suggestion", async () => {
  const h = mount(
    "ai-late",
    "P20",
    "/tasks/new?mode=monitor",
    <TaskWizardPage />,
  );
  await waitFor(() =>
    expect(h.control.snapshot().pendingSuggestions).toBeGreaterThan(0),
  );
  const schedule = structuredClone(draft().schedule);
  addTerm("TEST 人工保留词");
  act(() => h.control.releaseSuggestions());
  const dialog = await screen.findByRole("dialog", { name: "更新搜索建议" });
  expect(draft().terms.map((t: { value: string }) => t.value)).toEqual([
    "TEST 人工保留词",
  ]);
  fireEvent.click(within(dialog).getByRole("button", { name: "合并新增建议" }));
  await screen.findByRole("button", { name: "TEST 后到展台需求建议" });
  expect(draft().terms.map((t: { value: string }) => t.value)).toContain(
    "TEST 人工保留词",
  );
  expect(draft().schedule).toEqual(schedule);
  expect(h.events.some((e) => e.operation === "startTask")).toBe(false);
});
it("P06 cancellation ignores the same transport response when it is released later", async () => {
  const h = mount("ai-late", "P06", "/tasks/new", <TaskWizardPage />);
  await waitFor(() =>
    expect(h.control.snapshot().pendingSuggestions).toBeGreaterThan(0),
  );
  fireEvent.click(screen.getByRole("button", { name: "取消生成" }));
  await act(async () => h.control.releaseSuggestions());
  expect(
    screen.queryByRole("button", { name: "TEST 后到展台需求建议" }),
  ).toBeNull();
  expect(screen.queryByRole("dialog", { name: "更新搜索建议" })).toBeNull();
});
it("P13 real route binds UNKNOWN to the original request; only an explicit non-delivery lookup unlocks", async () => {
  const h = mount(
    "send-unknown",
    "P13",
    "/outreach?opportunity=TEST-opportunity&channel=comment",
    <OutreachPage />,
  );
  const prepare = await screen.findByRole("button", { name: "准备发送" });
  expect((prepare as HTMLButtonElement).disabled).toBe(true);
  // Persist routing metadata through the real component callback before sending.
  const save = await screen.findByRole("button", { name: "保存草稿" });
  await waitFor(() => expect((save as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(save);
  await waitFor(() =>
    expect((prepare as HTMLButtonElement).disabled).toBe(false),
  );
  fireEvent.click(prepare);
  fireEvent.click(
    await screen.findByRole("button", { name: /核验发送条件|核对发送信息/ }),
  );
  await screen.findByText("TEST 合成收件人（不会实际发送）");
  fireEvent.click(
    screen.getByRole("checkbox", { name: "我已核对联系对象、发送账号和内容" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "确认并发送" }));
  await waitFor(() => expect(h.control.snapshot().phase).toBe("UNKNOWN"));
  fireEvent.click(
    await screen.findByRole("button", { name: "核对原发送结果" }),
  );
  await waitFor(() =>
    expect(
      h.events.some((e) => e.operation === "recovery.send.reconcile"),
    ).toBe(true),
  );
  expect(Object.values(ledger("send-attempts"))).toContain("PENDING");
  expect(
    (screen.getByRole("button", { name: "确认并发送" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  act(() => h.control.confirmNotExecuted());
  fireEvent.click(screen.getByRole("button", { name: "核对原发送结果" }));
  await waitFor(() => expect(ledger("send-attempts")).toEqual({}));
  expect(
    (screen.getByRole("button", { name: "确认并发送" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  expect(
    h.events.filter((e) => e.operation === "recovery.send.unknown"),
  ).toHaveLength(1);
});
it("P19 real page queries the original UNKNOWN startup and never invents an accepted task", async () => {
  const h = mount(
    "start-unknown",
    "P19",
    "/tasks/new?step=confirm",
    <TaskWizardPage />,
  );
  const start = await screen.findByRole("button", { name: "确认并启动" });
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: "我已核对以上业务画像、搜索条件、账号与运行设置",
    }),
  );
  await waitFor(() =>
    expect((start as HTMLButtonElement).disabled).toBe(false),
  );
  fireEvent.click(start);
  await waitFor(() => expect(h.control.snapshot().phase).toBe("UNKNOWN"));
  await screen.findByText("启动结果尚未确认，请先检查任务列表，避免重复创建。");
  fireEvent.click(
    await screen.findByRole("button", { name: "核对原启动结果" }),
  );
  await waitFor(() =>
    expect(
      h.events.some((e) => e.operation === "recovery.start.reconcile"),
    ).toBe(true),
  );
  expect(Object.keys(ledger("unknown-task-starts"))).toHaveLength(1);
  act(() => h.control.confirmNotExecuted());
  fireEvent.click(screen.getByRole("button", { name: "核对原启动结果" }));
  await waitFor(() => expect(ledger("unknown-task-starts")).toEqual({}));
  await waitFor(() =>
    expect(screen.queryByText("启动结果尚未确认，请先检查任务列表，避免重复创建。")).toBeNull(),
  );
  expect((start as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole("checkbox", {
    name: "我已核对以上业务画像、搜索条件、账号与运行设置",
  }) as HTMLInputElement).checked).toBe(false);
  expect(location.hash).toBe("#/tasks/new?step=confirm");
  expect(
    h.events.filter((e) => e.operation === "recovery.start.unknown"),
  ).toHaveLength(1);
});
it("P17 capability-insufficient connection returns through real hashchange without losing the task draft", async () => {
  const route =
    "/connections?connect=xhs&returnTo=" +
    encodeURIComponent("/tasks/new?step=connect");
  const h = mount("connection-limited", "P17", route, <ConnectionsPage />);
  sessionStorage.setItem(
    `yike.ui.draft.v1.task.${TEST_USER}`,
    JSON.stringify({ id: "TEST-return-draft", name: "TEST 保留配置" }),
  );
  fireEvent.click(await screen.findByRole("button", { name: "打开登录窗口" }));
  await screen.findByText("等待登录");
  fireEvent.click(
    screen.getByRole("button", { name: "我已完成登录，检查连接" }),
  );
  await screen.findByText(
    "账号连接成功，但尚无已验证的采集或触达能力；任务启动条件仍需检查。",
  );
  fireEvent.click(screen.getByRole("button", { name: "完成并返回" }));
  await waitFor(() => expect(location.hash).toBe("#/tasks/new?step=connect"));
  expect(draft().name).toBe("TEST 保留配置");
  expect(
    h.events.some((e) => e.operation === "recovery.connection.limited"),
  ).toBe(true);
});
