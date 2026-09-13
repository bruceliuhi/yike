// @vitest-environment jsdom
import { beforeEach, afterEach, it, expect, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import { PendingTaskStarts } from "../../src/renderer/pages/tasks/PendingTaskStarts";
import {
  useOperationLedger,
  operationLedgerKey,
} from "../../src/renderer/app/operationLedger";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import {
  startEntry,
  type TaskStartBinding,
} from "../../src/renderer/domain/taskOperations";
import type { AppContextValue } from "../../src/renderer/app/context";
import type { YikeService } from "../../src/renderer/services/contracts";
import { parseRoute } from "../../src/renderer/domain/routes";
let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
const binding: TaskStartBinding = {
  draftId: "draft-test",
  requestId: "task:draft-test:2",
  revision: 2,
  configurationHash: "a".repeat(64),
  mode: "once",
};
const run = {
  id: "run-test",
  name: "核对测试任务",
  mode: "once",
  platforms: ["web"],
  status: "PENDING",
};
function key() {
  return operationLedgerKey("unknown-task-starts", context.session.userId!);
}
function stored() {
  return JSON.parse(localStorage.getItem(key()) || "{}");
}
beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  context = {
    service: {
      taskOperations: {
        reconcileStart: vi.fn(async (input) => ({
          ...input,
          status: "ACCEPTED",
          run,
        })),
        start: vi.fn(),
      },
    } as unknown as YikeService,
    session: { authenticated: true, userId: crypto.randomUUID() },
    sessionReady: true,
    route: parseRoute("#/collection"),
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
function seed(entry = startEntry(binding)) {
  localStorage.setItem(key(), JSON.stringify({ [binding.draftId]: entry }));
}
it('keeps unresolved startup recovery visible with the request ID removed',()=>{
 seed();render(<PendingTaskStarts/>);
 expect(screen.queryByText(binding.requestId)).toBeNull();
 expect(screen.getByRole('button',{name:'核对原启动结果'})).toBeTruthy();
 expect(screen.getByText('启动结果待确认').closest('details')).toBeNull();
});
it('distinguishes multiple startup records while querying only the selected original binding',async()=>{
 const second={...binding,draftId:'z-other-draft',requestId:'task:z-other-draft:2'};
 localStorage.setItem(key(),JSON.stringify({[second.draftId]:startEntry(second),[binding.draftId]:startEntry(binding)}));
 render(<PendingTaskStarts/>);
 expect(screen.getByText('启动记录 1')).toBeTruthy();
 const row=screen.getByText('启动记录 2').closest('.task-recovery-row')!;
 fireEvent.click(row.querySelector('button')!);
 await waitFor(()=>expect(context.service.taskOperations!.reconcileStart).toHaveBeenCalledWith(second));
 expect(context.service.taskOperations!.start).not.toHaveBeenCalled();
});
it("recovers the same original request after clearing drafts and remounting, without starting anything", async () => {
  seed();
  const view = render(<PendingTaskStarts />);
  view.unmount();
  clearLocalDrafts();
  render(<PendingTaskStarts />);
  fireEvent.click(screen.getByRole("button", { name: "核对原启动结果" }));
  await screen.findByText("已核对任务：核对测试任务");
  expect(context.service.taskOperations!.reconcileStart).toHaveBeenCalledWith(
    binding,
  );
  expect(context.service.taskOperations!.start).not.toHaveBeenCalled();
  expect(stored()).toEqual({});
});
it.each([
  "mismatch",
  "pending",
  "network",
  "rejection-without-proof",
  "legacy",
])("retains the original lock on %s", async (kind) => {
  seed(kind === "legacy" ? "task:draft-test:2" : undefined);
  const receipt = { ...binding, status: "ACCEPTED", run };
  context.service.taskOperations!.reconcileStart = vi
    .fn()
    .mockImplementation(async () => {
      if (kind === "network") throw new Error("离线测试");
      if (kind === "mismatch")
        return { ...receipt, configurationHash: "b".repeat(64) };
      if (kind === "pending") return { ...binding, status: "PENDING" };
      if (kind === "rejection-without-proof")
        return { ...binding, status: "REJECTED" };
      return receipt;
    });
  render(<PendingTaskStarts />);
  fireEvent.click(screen.getByRole("button", { name: "核对原启动结果" }));
  await waitFor(() =>
    expect(
      (
        screen.getByRole("button", {
          name: "核对原启动结果",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false),
  );
  expect(stored()[binding.draftId]).toBeTruthy();
  expect(context.service.taskOperations!.start).not.toHaveBeenCalled();
  expect(screen.queryByText("已核对任务：核对测试任务")).toBeNull();
});
it("requires definitive rejected confirmation before releasing the original record", async () => {
  seed();
  context.service.taskOperations!.reconcileStart = vi.fn().mockResolvedValue({
    ...binding,
    status: "REJECTED",
    confirmedNotStarted: true,
  });
  const settled = vi.fn();
  render(<PendingTaskStarts onSettled={settled} />);
  fireEvent.click(screen.getByRole("button", { name: "核对原启动结果" }));
  await waitFor(() => expect(stored()).toEqual({}));
  expect(settled).toHaveBeenCalledWith("REJECTED", binding);
});
it("bounds reconciliation waiting and ignores a late response after timeout", async () => {
  vi.useFakeTimers();
  seed();
  let resolve!: (value: unknown) => void;
  context.service.taskOperations!.reconcileStart = vi.fn(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  ) as never;
  render(<PendingTaskStarts />);
  fireEvent.click(screen.getByRole("button", { name: "核对原启动结果" }));
  await act(() => vi.advanceTimersByTimeAsync(30_001));
  expect(screen.getByText(/原启动请求核对超时/)).toBeTruthy();
  await act(async () => resolve({ ...binding, status: "ACCEPTED", run }));
  expect(stored()[binding.draftId]).toBeTruthy();
});
it("does not route or publish another identity after the original account leaves", async () => {
  seed();
  let resolve!: (value: unknown) => void;
  context.service.taskOperations!.reconcileStart = vi.fn(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  ) as never;
  const accepted = vi.fn();
  const view = render(<PendingTaskStarts onAccepted={accepted} />);
  fireEvent.click(screen.getByRole("button", { name: "核对原启动结果" }));
  await waitFor(() => expect(resolve).toBeTypeOf("function"));
  context = {
    ...context,
    session: { authenticated: true, userId: "different-user" },
  };
  view.rerender(<PendingTaskStarts onAccepted={accepted} />);
  await act(async () => resolve({ ...binding, status: "ACCEPTED", run }));
  expect(accepted).not.toHaveBeenCalled();
  expect(context.notify).not.toHaveBeenCalled();
  expect(screen.queryByText(/核对测试任务/)).toBeNull();
});
it("validates new binding values and retains legacy locks", () => {
  const { result } = renderHook(() =>
    useOperationLedger("unknown-task-starts", context.session.userId),
  );
  act(() =>
    result.current[1]({
      [binding.draftId]: startEntry(binding),
      legacy: "task:legacy:1",
    }),
  );
  expect(stored().legacy).toBe("task:legacy:1");
  expect(() =>
    act(() =>
      result.current[1]({
        [binding.draftId]: startEntry({
          ...binding,
          configurationHash: "wrong",
        }),
      }),
    ),
  ).toThrow();
  expect(() =>
    act(() =>
      result.current[1]({
        [binding.draftId]: startEntry({ ...binding, requestId: "other" }),
      }),
    ),
  ).toThrow();
  expect(stored().legacy).toBe("task:legacy:1");
});
