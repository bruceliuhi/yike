// @vitest-environment jsdom
import { beforeEach, afterEach, it, expect, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { TasksPage } from "../../src/renderer/pages/Tasks";
import { operationLedgerKey } from "../../src/renderer/app/operationLedger";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import {
  actionEntry,
  type TaskActionBinding,
} from "../../src/renderer/domain/taskOperations";
import type { AppContextValue } from "../../src/renderer/app/context";
import type { YikeService } from "../../src/renderer/services/contracts";
import type { TaskRun } from "../../src/renderer/domain/models";
import { parseRoute } from "../../src/renderer/domain/routes";
let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
let run: TaskRun;
function ops() {
  return context.service.taskOperations!;
}
function key() {
  return operationLedgerKey("task-operations", context.session.userId!);
}
function stored() {
  return JSON.parse(localStorage.getItem(key()) || "{}");
}
beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  run = {
    id: "run-test",
    name: "真实契约测试任务",
    mode: "monitor",
    platforms: ["web"],
    status: "RUNNING",
    updatedAt: "2026-09-09T00:00:00Z",
  };
  context = {
    service: {
      tasks: vi.fn(async () => [run]),
      taskOperations: {
        task: vi.fn(async () => run),
        action: vi.fn(async (input) => ({
          ...input,
          status: "APPLIED",
          run: { ...run, status: "PAUSED" },
        })),
        reconcileAction: vi.fn(),
        start: vi.fn(),
      },
    } as unknown as YikeService,
    session: { authenticated: true, userId: crypto.randomUUID() },
    sessionReady: true,
    route: parseRoute("#/monitors/run-test"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
  };
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});
async function confirm(label = "暂停任务") {
  await screen.findByRole("button", { name: label });
  fireEvent.click(screen.getByRole("button", { name: label }));
  return within(screen.getByRole("dialog", { name: label + "？" })).getByRole(
    "button",
    { name: "确认" },
  );
}
it.each([
  ["RUNNING", "暂停任务", "pause", "PAUSED"],
  ["PAUSED", "恢复任务", "resume", "RUNNING"],
  ["FAILED", "重试任务", "retry", "PENDING"],
  ["PENDING", "取消任务", "cancel", "CANCELED"],
] as const)(
  "confirms %s with a single original request and actual transition",
  async (status, label, action, next) => {
    run = { ...run, status };
    let resolve!: (value: unknown) => void;
    ops().action = vi.fn(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    ) as never;
    render(<TasksPage />);
    const button = await confirm(label);
    fireEvent.click(button);
    fireEvent.click(button);
    await waitFor(() => expect(ops().action).toHaveBeenCalledOnce());
    expect(context.notify).not.toHaveBeenCalled();
    const binding = vi.mocked(ops().action).mock.calls[0][0];
    expect(binding.action).toBe(action);
    expect(binding.taskId).toBe(run.id);
    expect(binding.expectedHash).toMatch(/^[a-f0-9]{64}$/);
    expect(stored()[actionEntry(binding)]).toBe("PENDING");
    expect((button as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(button);
    expect(ops().action).toHaveBeenCalledOnce();
    await act(async () =>
      resolve({ ...binding, status: "APPLIED", run: { ...run, status: next } }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(stored()).toEqual({});
    expect(context.notify).toHaveBeenCalledWith(
      expect.stringContaining("已确认完成"),
      "success",
    );
    expect(context.service.tasks).toHaveBeenCalledOnce();
  },
);
it("refuses an unavailable service before recording or dispatching an operation", async () => {
  context.service.taskOperations = undefined;
  render(<TasksPage />);
  fireEvent.click(await confirm());
  await screen.findByText(/任务执行与原请求核对服务尚未接通/);
  expect(stored()).toEqual({});
  expect(context.notify).not.toHaveBeenCalled();
});
it("rejects a stale task preflight before dispatch", async () => {
  ops().task = vi.fn().mockResolvedValue({ ...run, status: "PAUSED" });
  render(<TasksPage />);
  fireEvent.click(await confirm());
  await screen.findByText(/任务状态已变化/);
  expect(ops().action).not.toHaveBeenCalled();
  expect(stored()).toEqual({});
});
it.each(["unmount", "identity", "route"])(
  "does not dispatch after leaving a pending preflight: %s",
  async (kind) => {
    let resolve!: (run: TaskRun) => void;
    ops().task = vi.fn(
      () =>
        new Promise<TaskRun>((done) => {
          resolve = done;
        }),
    );
    const view = render(<TasksPage />);
    fireEvent.click(await confirm());
    await waitFor(() => expect(resolve).toBeTypeOf("function"));
    if (kind === "unmount") view.unmount();
    else {
      context = {
        ...context,
        ...(kind === "identity"
          ? { session: { authenticated: true, userId: "other" } }
          : { route: parseRoute("#/monitors") }),
      };
      view.rerender(<TasksPage />);
    }
    await act(async () => resolve(run));
    expect(ops().action).not.toHaveBeenCalled();
    expect(context.notify).not.toHaveBeenCalled();
  },
);
it("does not execute if local persistence fails", async () => {
  render(<TasksPage />);
  const button = await confirm();
  const original = Storage.prototype.setItem;
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (
    this: Storage,
    k,
    v,
  ) {
    if (k.startsWith("yike.ui.operation."))
      throw new Error("test storage failure");
    return original.call(this, k, v);
  });
  fireEvent.click(button);
  await screen.findByText(/操作确认记录暂时无法可靠保存/);
  expect(ops().action).not.toHaveBeenCalled();
});
it.each(["wrong-id", "pending", "network", "rejected-without-proof"])(
  "keeps an unresolved %s action locked and recovers only the original request after remount",
  async (kind) => {
    ops().action = vi.fn().mockImplementation(async (binding) => {
      if (kind === "network") throw new Error("test network");
      if (kind === "wrong-id")
        return {
          ...binding,
          requestId: "wrong",
          status: "APPLIED",
          run: { ...run, status: "PAUSED" },
        };
      if (kind === "pending") return { ...binding, status: "PENDING" };
      return { ...binding, status: "REJECTED" };
    });
    const view = render(<TasksPage />);
    fireEvent.click(await confirm());
    await waitFor(() => expect(ops().action).toHaveBeenCalledOnce());
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "核对原操作" })).toBeTruthy(),
    );
    const binding = vi.mocked(ops().action).mock.calls[0][0];
    await waitFor(() =>
      expect(
        (
          within(screen.getByRole("dialog")).getByRole("button", {
            name: "确认",
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(true),
    );
    view.unmount();
    clearLocalDrafts();
    ops().reconcileAction = vi.fn().mockResolvedValue({
      ...binding,
      status: "APPLIED",
      run: { ...run, status: "PAUSED" },
    });
    render(<TasksPage />);
    await screen.findByRole("button", { name: "核对原操作" });
    fireEvent.click(screen.getByRole("button", { name: "核对原操作" }));
    await waitFor(() => expect(stored()).toEqual({}));
    expect(ops().reconcileAction).toHaveBeenCalledWith(binding);
    expect(ops().action).toHaveBeenCalledOnce();
    await screen.findByRole("button", { name: "恢复任务" });
  },
);
it("does not unlock another request on a mismatched query receipt", async () => {
  const binding: TaskActionBinding = {
    taskId: run.id,
    action: "pause",
    expectedHash: "a".repeat(64),
    requestId: "original",
  };
  localStorage.setItem(
    key(),
    JSON.stringify({ [actionEntry(binding)]: "PENDING" }),
  );
  ops().reconcileAction = vi.fn().mockResolvedValue({
    ...binding,
    requestId: "other",
    status: "REJECTED",
    confirmedNotApplied: true,
  });
  render(<TasksPage />);
  fireEvent.click(screen.getByRole("button", { name: "核对原操作" }));
  await screen.findByText(/任务操作回执与原请求不匹配/);
  expect(stored()[actionEntry(binding)]).toBe("PENDING");
  expect(context.notify).not.toHaveBeenCalled();
});
it("locks on timeout and ignores a late action response", async () => {
  const nativeDigest = crypto.subtle.digest.bind(crypto.subtle);
  let releaseDigest!: () => void;
  const digestGate = new Promise<void>((done) => { releaseDigest = done; });
  vi.spyOn(crypto.subtle, "digest").mockImplementation(async (...args) => {
    await digestGate;
    return nativeDigest(...args);
  });
  let resolve!: (v: unknown) => void;
  ops().action = vi.fn(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  ) as never;
  render(<TasksPage />);
  const button = await confirm();
  vi.useFakeTimers();
  fireEvent.click(button);
  await act(() => vi.advanceTimersByTimeAsync(1));
  // Fake timer ticks do not complete Web Crypto's real asynchronous digest.
  expect(ops().action).not.toHaveBeenCalled();
  await act(async () => {
    releaseDigest();
    await vi.waitFor(() => expect(ops().action).toHaveBeenCalledOnce());
  });
  const binding = vi.mocked(ops().action).mock.calls[0][0];
  await act(() => vi.advanceTimersByTimeAsync(30_001));
  expect(screen.getByText(/任务操作结果尚未确认，已保留原请求/)).toBeTruthy();
  await act(async () =>
    resolve({
      ...binding,
      status: "APPLIED",
      run: { ...run, status: "PAUSED" },
    }),
  );
  expect(stored()[actionEntry(binding)]).toBe("PENDING");
  expect(context.notify).not.toHaveBeenCalled();
});
it("re-reads durable locks after preflight even without a storage event, disabling a concurrent dispatch", async () => {
  let resolve!: (value: TaskRun) => void;
  ops().task = vi.fn(
    () =>
      new Promise<TaskRun>((done) => {
        resolve = done;
      }),
  );
  render(<TasksPage />);
  fireEvent.click(await confirm());
  await waitFor(() => expect(resolve).toBeTypeOf("function"));
  const original: TaskActionBinding = {
    taskId: run.id,
    action: "pause",
    requestId: "other-original",
    expectedHash: "a".repeat(64),
  };
  localStorage.setItem(
    key(),
    JSON.stringify({ [actionEntry(original)]: "PENDING" }),
  );
  await act(async () => resolve(run));
  await screen.findByText(/该任务已有操作待核对，当前没有重复提交/);
  expect(ops().action).not.toHaveBeenCalled();
  expect(stored()[actionEntry(original)]).toBe("PENDING");
});
it("releases only an explicitly confirmed unperformed original action without reporting success", async () => {
  ops().action = vi.fn(async (binding) => ({
    ...binding,
    status: "REJECTED",
    confirmedNotApplied: true,
    message: "已确认未执行测试操作",
  }));
  render(<TasksPage />);
  fireEvent.click(await confirm());
  await waitFor(() =>
    expect(context.notify).toHaveBeenCalledWith("已确认未执行测试操作", "info"),
  );
  expect(stored()).toEqual({});
  expect(screen.queryByRole("dialog")).toBeNull();
  await screen.findByRole("button", { name: "暂停任务" });
});
