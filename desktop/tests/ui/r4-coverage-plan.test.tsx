// @vitest-environment jsdom
import { webcrypto } from "node:crypto";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { AppContextValue } from "../../src/renderer/app/context";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { taskDraftOwner } from "../../src/renderer/app/taskDraft";
import { operationLedgerKey } from "../../src/renderer/app/operationLedger";
import { newTaskDraft, type TaskRun } from "../../src/renderer/domain/models";
import { CoveragePlanDrawer } from "../../src/renderer/pages/tasks/CoveragePlanDrawer";
import { CoverageAdjustmentRecovery } from "../../src/renderer/pages/tasks/CoverageAdjustmentRecovery";
import { TasksPage } from "../../src/renderer/pages/Tasks";
import { parseRoute } from "../../src/renderer/domain/routes";
import { coverageFixture, coverageRun } from "./r4-search-coverage-fixtures";
import {
  coverageConfirmationHash,
  readCoverageAdjustmentReceipt,
  readCoveragePreview,
  validCoverageAdjustmentEntry,
  type CoveragePlanPreview,
} from "../../src/renderer/domain/coveragePlan";
import type { YikeService } from "../../src/renderer/services/contracts";
import { applied, planFor, previewFor } from "./r4-coverage-plan-fixtures";
let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
beforeEach(() => {
  vi.stubGlobal("crypto", webcrypto);
  localStorage.clear();
  sessionStorage.clear();
  clearLocalDrafts();
  context = {
    session: {
      authenticated: true,
      userId: "TEST-user",
      accountScope: { id: "TEST-account", version: 1 },
    },
    service: {
      coveragePlans: {
        preview: vi.fn(async (input) => previewFor(input)),
        adjust: vi.fn(async ({ binding, preview }) =>
          applied(binding, preview),
        ),
        reconcile: vi.fn(),
      },
    } as unknown as YikeService,
    notify: vi.fn(),
    navigate: vi.fn(),
  } as unknown as AppContextValue;
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
const ledger = () =>
  JSON.parse(
    localStorage.getItem(
      operationLedgerKey("coverage-adjustments", context.session.userId!),
    ) || "{}",
  );
async function loadAdjust() {
  const plan = planFor("ADJUST_LIMIT");
  const view = render(<CoveragePlanDrawer plan={plan} onClose={vi.fn()} />);
  fireEvent.change(screen.getByRole("spinbutton", { name: "新的搜贝上限" }), {
    target: { value: "80" },
  });
  fireEvent.click(screen.getByRole("button", { name: "读取调整估算" }));
  await screen.findByText("30 搜贝");
  return { view, plan };
}
it("creates one editable local draft while retaining the active input and existing library", async () => {
  const owner = taskDraftOwner(
    context.session.userId,
    context.session.accountScope,
  );
  const current = { ...newTaskDraft(), name: "TEST当前人工输入" },
    existing = { ...newTaskDraft(), name: "TEST原草稿" };
  sessionStorage.setItem(
    "yike.ui.draft.v1.task." + owner,
    JSON.stringify(current),
  );
  sessionStorage.setItem(
    "yike.ui.draft.v1.task-library." + owner,
    JSON.stringify([existing]),
  );
  render(<CoveragePlanDrawer plan={planFor("NEW_DRAFT")} onClose={vi.fn()} />);
  await screen.findByText("TEST 已确认未查范围");
  const create = screen.getByRole("button", { name: "创建本机草稿" });
  expect((create as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("checkbox", { name: /我已核对本次范围/ }));
  fireEvent.click(create);
  fireEvent.click(create);
  await screen.findByText(/已创建本机会话草稿/);
  const rows = JSON.parse(
    sessionStorage.getItem("yike.ui.draft.v1.task-library." + owner)!,
  );
  expect(rows).toHaveLength(3);
  expect(rows.slice(0, 2)).toEqual([existing, current]);
  expect(rows[2].id).not.toBe("TEST-source-draft");
  expect(rows[2].revision).toBe(1);
  expect(rows[2].terms[0].value).toBe("TEST询价");
  expect(rows[2].research.coverageProvenance).toMatchObject({
    kind: "NEW_DRAFT",
    runId: "TEST-run",
    windowId: "TEST-window",
    unitId: "TEST-douyin",
    deduplicationVersion: "TEST-dedup-v1",
    accountScopeId: "TEST-account",
    scopeSummary: "TEST 已确认未查范围",
  });
  expect(JSON.stringify(rows[2])).not.toContain("authorizationToken");
  expect(
    JSON.parse(sessionStorage.getItem("yike.ui.draft.v1.task." + owner)!),
  ).toEqual(current);
  expect(context.service.coveragePlans!.adjust).not.toHaveBeenCalled();
});
it("requires a fresh exact cap preview and confirmation; adjustment never resumes", async () => {
  await loadAdjust();
  const button = screen.getByRole("button", { name: "确认调整上限" });
  expect((button as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("checkbox", { name: /我已核对本次范围/ }));
  fireEvent.change(screen.getByRole("spinbutton", { name: "新的搜贝上限" }), {
    target: { value: "90" },
  });
  expect((button as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "读取调整估算" }));
  await screen.findByText("40 搜贝");
  fireEvent.click(screen.getByRole("checkbox", { name: /我已核对本次范围/ }));
  fireEvent.click(button);
  fireEvent.click(button);
  await screen.findByText(/上限调整已确认，任务尚未恢复/);
  expect(context.service.coveragePlans!.adjust).toHaveBeenCalledOnce();
  expect(ledger()).toEqual({});
  expect(context.notify).toHaveBeenCalledWith(
    "搜贝上限已调整为 90；任务尚未恢复。",
    "success",
  );
});
it("keeps UNKNOWN through close and draft cleanup, and only reconciles the original immutable snapshot", async () => {
  vi.mocked(context.service.coveragePlans!.adjust).mockImplementation(
    async ({ binding }) => ({ binding, status: "UNKNOWN" }),
  );
  const { view, plan } = await loadAdjust();
  fireEvent.click(screen.getByRole("checkbox", { name: /我已核对本次范围/ }));
  fireEvent.click(screen.getByRole("button", { name: "确认调整上限" }));
  await screen.findByText(/上限调整结果仍待核对/);
  const input = vi.mocked(context.service.coveragePlans!.adjust).mock
    .calls[0][0];
  const before = ledger();
  view.unmount();
  clearLocalDrafts();
  render(<CoverageAdjustmentRecovery taskId={plan.taskId} />);
  const result = applied(input.binding, input.preview);
  vi.mocked(context.service.coveragePlans!.reconcile).mockResolvedValue({
    ...result,
    maximum: 100,
  } as typeof result);
  fireEvent.click(screen.getByRole("button", { name: "核对原上限调整" }));
  await screen.findByText(/回执未确认原预算版本/);
  expect(ledger()).toEqual(before);
  vi.mocked(context.service.coveragePlans!.reconcile).mockResolvedValue(result);
  fireEvent.click(screen.getByRole("button", { name: "核对原上限调整" }));
  await waitFor(() => expect(ledger()).toEqual({}));
  expect(context.service.coveragePlans!.adjust).toHaveBeenCalledOnce();
  expect(context.service.coveragePlans!.reconcile).toHaveBeenLastCalledWith(
    input.binding,
  );
});
it("does not dispatch on failed durable storage or update a new identity after delayed preview", async () => {
  await loadAdjust();
  fireEvent.click(screen.getByRole("checkbox", { name: /我已核对本次范围/ }));
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("storage failed");
  });
  fireEvent.click(screen.getByRole("button", { name: "确认调整上限" }));
  await screen.findByText(/操作确认记录暂时无法可靠保存/);
  expect(context.service.coveragePlans!.adjust).not.toHaveBeenCalled();
});
it("ignores delayed preview after account scope changes", async () => {
  let resolve!: (v: CoveragePlanPreview) => void;
  vi.mocked(context.service.coveragePlans!.preview).mockImplementation(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  const plan = planFor("NEW_DRAFT");
  const view = render(<CoveragePlanDrawer plan={plan} onClose={vi.fn()} />);
  await waitFor(() =>
    expect(context.service.coveragePlans!.preview).toHaveBeenCalledOnce(),
  );
  const input = vi.mocked(context.service.coveragePlans!.preview).mock
    .calls[0][0];
  context = {
    ...context,
    session: { ...context.session, accountScope: { id: "OTHER", version: 1 } },
  };
  view.rerender(<CoveragePlanDrawer plan={plan} onClose={vi.fn()} />);
  await act(async () => resolve(previewFor(input)));
  expect(screen.queryByText("TEST 已确认未查范围")).toBeNull();
  expect(
    (screen.getByRole("button", { name: "创建本机草稿" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
});
it("shows unavailable preview honestly without creating a draft", async () => {
  delete context.service.coveragePlans;
  render(<CoveragePlanDrawer plan={planFor("NEW_DRAFT")} onClose={vi.fn()} />);
  await screen.findByText(/预览服务尚未接通/);
  expect(
    (screen.getByRole("button", { name: "创建本机草稿" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
});
it("connects the production task detail entry to a real preview drawer without an injected onPlan", async () => {
  context.route = parseRoute("#/monitors/" + coverageRun.id);
  context.service.tasks = vi.fn(async () => [coverageRun]);
  context.service.searchCoverage = {
    query: vi.fn(async (request) => {
      const snapshot = coverageFixture(request);
      snapshot.units[1].recovery = "TERMINAL";
      return snapshot;
    }),
  };
  render(<TasksPage />);
  fireEvent.click(
    await screen.findByRole("button", { name: "查看TEST 方案比较覆盖明细" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "基于未查范围创建草稿" }));
  await screen.findByRole("dialog", { name: "基于未查范围创建草稿" });
  await screen.findByText("TEST 已确认未查范围");
  expect(context.service.coveragePlans!.preview).toHaveBeenCalledOnce();
});
it("creates new tasks with research limits and hides old task rows on same-user scope changes", async () => {
  context.route = parseRoute("#/collection");
  context.service.tasks = vi.fn(async () => []);
  const view = render(<TasksPage />);
  fireEvent.click(screen.getByRole("button", { name: "新建获客任务" }));
  const owner = taskDraftOwner(
    context.session.userId,
    context.session.accountScope,
  );
  const saved = JSON.parse(
    sessionStorage.getItem("yike.ui.draft.v1.task." + owner)!,
  );
  expect(saved.research.version).toBe(1);
  expect(saved.research.maxSoubei).toBeNull();
  context = {
    ...context,
    route: parseRoute("#/monitors"),
    service: { ...context.service, tasks: vi.fn(async () => [coverageRun]) },
  };
  view.rerender(<TasksPage />);
  await screen.findByText(coverageRun.name);
  context.service.tasks = vi.fn(() => new Promise<TaskRun[]>(() => {}));
  context = {
    ...context,
    session: {
      ...context.session,
      accountScope: { id: "OTHER-space", version: 2 },
    },
  };
  view.rerender(<TasksPage />);
  expect(screen.queryByText(coverageRun.name)).toBeNull();
});
it("does not query an adjustment from another account scope", async () => {
  vi.mocked(context.service.coveragePlans!.adjust).mockImplementation(
    async ({ binding }) => ({ binding, status: "UNKNOWN" }),
  );
  const { view, plan } = await loadAdjust();
  fireEvent.click(screen.getByRole("checkbox", { name: /我已核对本次范围/ }));
  fireEvent.click(screen.getByRole("button", { name: "确认调整上限" }));
  await screen.findByText(/上限调整结果仍待核对/);
  const before = ledger();
  view.unmount();
  context = {
    ...context,
    session: {
      ...context.session,
      accountScope: { id: "OTHER-space", version: 1 },
    },
  };
  render(<CoverageAdjustmentRecovery taskId={plan.taskId} />);
  expect(screen.queryByRole("button", { name: "核对原上限调整" })).toBeNull();
  expect(ledger()).toEqual(before);
  expect(context.service.coveragePlans!.reconcile).not.toHaveBeenCalled();
});
it("discards a rejected confirmation and requires a new preview before another adjustment", async () => {
  vi.mocked(context.service.coveragePlans!.adjust).mockImplementation(
    async ({ binding, preview }) => {
      const receipt = applied(binding, preview);
      if (receipt.status !== "APPLIED") throw new Error();
      return {
        binding,
        status: "REJECTED",
        confirmedNotApplied: true,
        confirmation: receipt.confirmation,
      };
    },
  );
  await loadAdjust();
  fireEvent.click(screen.getByRole("checkbox", { name: /我已核对本次范围/ }));
  fireEvent.click(screen.getByRole("button", { name: "确认调整上限" }));
  await screen.findByText(/原请求已确认未调整上限/);
  expect(ledger()).toEqual({});
  expect(
    (screen.getByRole("button", { name: "确认调整上限" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  expect(
    screen.queryByRole("checkbox", { name: /我已核对本次范围/ }),
  ).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "读取调整估算" }));
  await screen.findByText("30 搜贝");
  expect(
    (screen.getByRole("button", { name: "确认调整上限" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  expect(context.service.coveragePlans!.preview).toHaveBeenCalledTimes(2);
  expect(context.service.coveragePlans!.adjust).toHaveBeenCalledOnce();
});
it.each(["scope", "expiry", "difference", "budget"])(
  "rejects mismatched preview %s",
  async (kind) => {
    const input = {
      requestId: "TEST-request",
      plan: planFor("ADJUST_LIMIT"),
      newMaxSoubei: 80,
    };
    const value = previewFor(input);
    if (value.kind !== "ADJUST_LIMIT") throw new Error();
    if (kind === "scope") value.quote.accountScopeId = "other";
    if (kind === "expiry")
      value.expiresAt = new Date(Date.now() - 1).toISOString();
    if (kind === "difference") value.quote.additionalSoubei = 31;
    if (kind === "budget") value.quote.budgetRevision = 2;
    expect(() => readCoveragePreview(value, input, context.session)).toThrow();
  },
);
it("binds all terminal receipt facts to the exact confirmed preview and rejects malformed ledger records", async () => {
  const input = {
    requestId: "TEST-request",
    plan: planFor("ADJUST_LIMIT"),
    newMaxSoubei: 80,
  };
  const preview = readCoveragePreview(
    previewFor(input),
    input,
    context.session,
  );
  const binding = {
    accountScopeId: input.plan.accountScopeId,
    scopeVersion: 1,
    taskId: input.plan.taskId,
    requestId: "TEST-adjust",
    confirmationHash: await coverageConfirmationHash(preview),
  };
  const result = applied(binding, preview);
  expect((await readCoverageAdjustmentReceipt(result, binding)).status).toBe(
    "APPLIED",
  );
  if (result.status !== "APPLIED") throw new Error();
  result.confirmation.quote.newMaxSoubei = 100;
  await expect(readCoverageAdjustmentReceipt(result, binding)).rejects.toThrow(
    /原确认快照/,
  );
  expect(
    validCoverageAdjustmentEntry(
      JSON.stringify([
        binding.accountScopeId,
        1,
        binding.taskId,
        binding.requestId,
        binding.confirmationHash,
      ]),
      "PENDING",
    ),
  ).toBe(true);
  expect(
    validCoverageAdjustmentEntry('["space",1,"task","req","bad"]', "PENDING"),
  ).toBe(false);
});
