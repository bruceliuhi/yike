// @vitest-environment jsdom
import { StrictMode } from "react";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { newTaskDraft, type TaskDraft } from "../../src/renderer/domain/models";
import type { AppContextValue } from "../../src/renderer/app/context";
import { parseRoute } from "../../src/renderer/domain/routes";
import { service } from "../../src/renderer/services/client";
import { ServiceError } from "../../src/renderer/services/contracts";
import type { ResearchStrategiesService } from "../../src/renderer/services/researchStrategies";
import type { PrepareStrategyRequest, StrategyReceipt, StrategyView } from "../../src/shared/researchStrategies";
import { operationLedgerKey } from "../../src/renderer/app/operationLedger";
import * as strategyConfirmationHook from "../../src/renderer/pages/tasks/useStrategyConfirmation";

let context: AppContextValue;
let draft: TaskDraft;
let fake: ReturnType<typeof serverFixture>;
const limits = { max_records: 10, max_runtime_seconds: 600 };
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
async function implementation() {
  return strategyConfirmationHook;
}
// Explicit in-memory UI fixture. Actual transport/PG is verified separately.
function serverFixture() {
  const receipts = new Map<string, StrategyReceipt>();
  let prepared: StrategyReceipt | null = null;
  let state: StrategyReceipt["state"] = "DRAFT";
  const instant = "2026-09-10T00:00:00Z";
  const api = {
    prepare: vi.fn(async (request: PrepareStrategyRequest): Promise<unknown> => {
      expect(localStorage.getItem(operationLedgerKey("research-strategy-operations", context.session.userId!))).toContain(request.request_id);
      const id = crypto.randomUUID();
      prepared = { schema_version: "strategy-confirmation-v1", request_id: request.request_id, operation: "PREPARE",
        strategy_version_id: id, draft_id: request.draft_id, draft_revision: request.draft_revision, profile_version_id: request.profile_version_id,
        profile_sha256: "a".repeat(64), configuration_sha256: "b".repeat(64), snapshot: { strategy_version_id: id,
          profile_version_id: request.profile_version_id, configuration: request.configuration, platforms: request.platforms,
          max_records: request.max_records, max_runtime_seconds: request.max_runtime_seconds }, state: "DRAFT", recorded_at: instant };
      state = "DRAFT";
      receipts.set(request.request_id, structuredClone(prepared));
      return structuredClone(prepared);
    }),
    confirm: vi.fn<ResearchStrategiesService["confirm"]>(async request => {
      expect(localStorage.getItem(operationLedgerKey("research-strategy-operations", context.session.userId!))).toContain(request.request_id);
      state = "CONFIRMED";
      const result: StrategyReceipt = { ...prepared!, request_id: request.request_id, operation: "CONFIRM", state };
      receipts.set(request.request_id, result);
      return structuredClone(result);
    }),
    revoke: vi.fn<ResearchStrategiesService["revoke"]>(async request => {
      state = "REVOKED";
      const result: StrategyReceipt = { ...prepared!, request_id: request.request_id, operation: "REVOKE", state };
      receipts.set(request.request_id, result);
      return structuredClone(result);
    }),
    getReceipt: vi.fn<ResearchStrategiesService["getReceipt"]>(async id => {
      if (!receipts.has(id)) throw new ServiceError("request_not_found", "未找到", 404);
      return structuredClone(receipts.get(id));
    }),
    getStrategy: vi.fn<ResearchStrategiesService["getStrategy"]>(async () => {
      const { request_id: _request, operation: _operation, recorded_at: _recorded, ...core } = prepared!;
      const view: StrategyView = { ...core, state, created_at: instant, confirmed_at: state === "CONFIRMED" ? instant : null,
        revoked_at: state === "REVOKED" ? instant : null, is_current: true, profile_current: true };
      return view;
    }),
  } satisfies ResearchStrategiesService;
  return { api, receipts };
}
beforeEach(() => {
  draft = { ...newTaskDraft(), name: "合成策略客户场景", profileId: crypto.randomUUID(), profileVersion: 1,
    terms: [{ id: "term", value: "设备采购", origin: "manual", edited: true }], platforms: ["web"] };
  fake = serverFixture();
  context = { service: { ...service, researchStrategies: fake.api }, session: { authenticated: true, userId: crypto.randomUUID() },
    route: parseRoute("#/tasks/new?step=confirm"), navigate: vi.fn(), notify: vi.fn(), refreshSession: vi.fn() };
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); });

describe("strategy confirmation hook", () => {
  it("does not submit from StrictMode render; persists before one prepare and requires an explicit confirmation", async () => {
    const { useStrategyConfirmation } = await implementation();
    const hook = renderHook(() => useStrategyConfirmation(draft, limits), { wrapper: StrictMode });
    expect(fake.api.prepare).not.toHaveBeenCalled();
    await act(async () => { await Promise.all([hook.result.current.prepare(), hook.result.current.prepare()]); });
    expect(fake.api.prepare).toHaveBeenCalledTimes(1);
    expect(hook.result.current.prepared).toBeTruthy();
    expect(hook.result.current.confirmed).toBe(false);
    await act(async () => { await hook.result.current.confirm(false); });
    expect(fake.api.confirm).not.toHaveBeenCalled();
    await act(async () => { await Promise.all([hook.result.current.confirm(true), hook.result.current.confirm(true)]); });
    expect(fake.api.confirm).toHaveBeenCalledTimes(1);
    expect(hook.result.current.confirmed).toBe(true);
    await act(async () => { await hook.result.current.revoke(); });
    expect(hook.result.current.confirmed).toBe(false);
  });

  it("does not send when the ledger cannot be saved", async () => {
    const { useStrategyConfirmation } = await implementation();
    const hook = renderHook(() => useStrategyConfirmation(draft, limits));
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota"); });
    await act(async () => { await hook.result.current.prepare(); });
    expect(fake.api.prepare).not.toHaveBeenCalled();
    expect(hook.result.current.error).toBeTruthy();
  });

  it("keeps an unknown request through 404 and retries only the same UUID after an explicit action", async () => {
    const { useStrategyConfirmation } = await implementation();
    fake.api.prepare.mockRejectedValueOnce(new ServiceError("SERVICE_TIMEOUT", "超时"));
    const hook = renderHook(() => useStrategyConfirmation(draft, limits));
    await act(async () => { await hook.result.current.prepare(); });
    const first = fake.api.prepare.mock.calls[0][0];
    expect(hook.result.current.pending).toBe(true);
    await act(async () => { await hook.result.current.reconcile(); });
    expect(hook.result.current.pending).toBe(true);
    await act(async () => { await hook.result.current.prepare(); });
    expect(fake.api.prepare).toHaveBeenCalledTimes(1);
    await act(async () => { await hook.result.current.retry(); });
    expect(fake.api.prepare.mock.calls[1][0]).toEqual(first);
    expect(hook.result.current.pending).toBe(false);
  });

  it("restores history after remount without restoring user confirmation", async () => {
    const { useStrategyConfirmation } = await implementation();
    const first = renderHook(() => useStrategyConfirmation(draft, limits));
    await act(async () => { await first.result.current.prepare(); });
    await act(async () => { await first.result.current.confirm(true); });
    first.unmount();
    const next = renderHook(() => useStrategyConfirmation(draft, limits));
    await act(async () => { await next.result.current.reconcile(); });
    expect(next.result.current.prepared).toBeTruthy();
    expect(next.result.current.confirmed).toBe(false);
    await act(async () => { await next.result.current.confirm(true); });
    expect(next.result.current.confirmed).toBe(true);
    expect(fake.api.confirm).toHaveBeenCalledTimes(1);
  });

  it("invalidates confirmation immediately on draft or budget changes", async () => {
    const { useStrategyConfirmation } = await implementation();
    const hook = renderHook(({ cap }) => useStrategyConfirmation(draft, cap), { initialProps: { cap: limits } });
    await act(async () => { await hook.result.current.prepare(); });
    await act(async () => { await hook.result.current.confirm(true); });
    expect(hook.result.current.confirmed).toBe(true);
    hook.rerender({ cap: { ...limits, max_records: 11 } });
    expect(hook.result.current.confirmed).toBe(false);
    draft = { ...draft, name: "已修改", revision: 2 };
    hook.rerender({ cap: limits });
    expect(hook.result.current.confirmed).toBe(false);
  });

  it("settles only the original user's opaque ledger and hides late data after an account switch", async () => {
    const { useStrategyConfirmation } = await implementation();
    let release!: (value: unknown) => void;
    const ordinary = fake.api.prepare.getMockImplementation()!;
    fake.api.prepare.mockImplementationOnce(async request => {
      const response = await ordinary(request);
      return new Promise(resolve => { release = () => resolve(response); });
    });
    const originalUser = context.session.userId!;
    const hook = renderHook(() => useStrategyConfirmation(draft, limits));
    let pending!: Promise<unknown>;
    act(() => { pending = hook.result.current.prepare(); });
    await waitFor(() => expect(release).toBeTypeOf("function"));
    context = { ...context, session: { authenticated: true, userId: crypto.randomUUID() } };
    hook.rerender();
    await act(async () => { release(null); await pending; });
    expect(hook.result.current.prepared).toBeNull();
    expect(hook.result.current.confirmed).toBe(false);
    expect(localStorage.getItem(operationLedgerKey("research-strategy-operations", originalUser))).toContain("RECORDED");
    expect(localStorage.getItem(operationLedgerKey("research-strategy-operations", context.session.userId!))).toBeNull();
  });

  it("retains the original lock for a mismatched receipt and preserves the legacy injected path", async () => {
    const { useStrategyConfirmation } = await implementation();
    const ordinary = fake.api.prepare.getMockImplementation()!;
    fake.api.prepare.mockImplementationOnce(async request => ({ ...(await ordinary(request) as StrategyReceipt), draft_revision: 999 }));
    const hook = renderHook(() => useStrategyConfirmation(draft, limits));
    await act(async () => { await hook.result.current.prepare(); });
    expect(hook.result.current.pending).toBe(true);
    expect(hook.result.current.prepared).toBeNull();
    context = { ...context, service: { ...context.service, researchStrategies: undefined } };
    hook.rerender();
    expect(hook.result.current.available).toBe(false);
    expect(hook.result.current.confirmed).toBe(false);
  });

  it.each(["account-scope", "service"] as const)(
    "returns false when a same-user %s change makes a waiting recheck stale",
    async change => {
      const { useStrategyConfirmation } = await implementation();
      const hook = renderHook(() => useStrategyConfirmation(draft, limits));
      await act(async () => { await hook.result.current.prepare(); });
      await act(async () => { await hook.result.current.confirm(true); });
      expect(hook.result.current.confirmed).toBe(true);

      let release!: () => void;
      const ordinary = fake.api.getStrategy.getMockImplementation()!;
      fake.api.getStrategy.mockImplementationOnce(async id => {
        const response = await ordinary(id);
        return new Promise(resolve => { release = () => resolve(response); });
      });
      let recheck!: Promise<boolean>;
      act(() => { recheck = hook.result.current.recheck(); });
      await waitFor(() => expect(release).toBeTypeOf("function"));
      context = change === "account-scope"
        ? { ...context, session: { ...context.session, accountScope: { id: "same-user-new-scope", version: 2 } } }
        : { ...context, service: { ...context.service } };
      hook.rerender();
      release();
      let result!: boolean;
      await act(async () => { result = await recheck; });
      expect(result).toBe(false);
      expect(hook.result.current.confirmed).toBe(false);
    },
  );

  it("reconciles changed or lost draft input only as history and never redispatches it", async () => {
    const { useStrategyConfirmation } = await implementation();
    const hook = renderHook(() => useStrategyConfirmation(draft, limits));
    await act(async () => { await hook.result.current.prepare(); });
    const prepareCalls = fake.api.prepare.mock.calls.length;

    draft = { ...draft, revision: draft.revision + 1, name: "", terms: [] };
    hook.rerender();
    await act(async () => { await hook.result.current.reconcile(); });
    expect(hook.result.current.historyOnly).toBe(true);
    expect(hook.result.current.prepared).toBeNull();
    await act(async () => {
      expect(await hook.result.current.retry()).toBe(false);
      expect(await hook.result.current.confirm(true)).toBe(false);
    });
    expect(fake.api.prepare).toHaveBeenCalledTimes(prepareCalls);
    expect(fake.api.confirm).not.toHaveBeenCalled();
  });

  it.each([
    { field: "is_current", value: false },
    { field: "profile_current", value: false },
    { field: "state", value: "REVOKED" },
  ] as const)("does not activate a confirmation when the current view has $field=$value", async change => {
    const { useStrategyConfirmation } = await implementation();
    const hook = renderHook(() => useStrategyConfirmation(draft, limits));
    await act(async () => { await hook.result.current.prepare(); });
    const ordinary = fake.api.getStrategy.getMockImplementation()!;
    let calls = 0;
    fake.api.getStrategy.mockImplementation(async id => {
      const response = await ordinary(id) as StrategyView;
      calls++;
      return calls === 2 ? { ...response, [change.field]: change.value } : response;
    });
    await act(async () => { await hook.result.current.confirm(true); });
    expect(fake.api.confirm).toHaveBeenCalledOnce();
    expect(hook.result.current.confirmed).toBe(false);
  });

  it("uses the real 30-second bound and ignores an eventual late recheck response", async () => {
    const { useStrategyConfirmation } = await implementation();
    const hook = renderHook(() => useStrategyConfirmation(draft, limits));
    await act(async () => { await hook.result.current.prepare(); });
    await act(async () => { await hook.result.current.confirm(true); });
    expect(hook.result.current.confirmed).toBe(true);

    vi.useFakeTimers();
    let release!: () => void;
    const ordinary = fake.api.getStrategy.getMockImplementation()!;
    fake.api.getStrategy.mockImplementationOnce(async id => {
      const response = await ordinary(id);
      return new Promise(resolve => { release = () => resolve(response); });
    });
    let pending!: Promise<boolean>;
    act(() => { pending = hook.result.current.recheck(); });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(release).toBeTypeOf("function");
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    await act(async () => { await vi.advanceTimersByTimeAsync(30_001); });
    expect(await pending).toBe(false);
    expect(hook.result.current.confirmed).toBe(false);
    release();
    await act(async () => { await Promise.resolve(); });
    expect(hook.result.current.confirmed).toBe(false);
  });

  it("does not POST confirm or revoke when their pending records cannot be saved", async () => {
    const { useStrategyConfirmation } = await implementation();
    const hook = renderHook(() => useStrategyConfirmation(draft, limits));
    await act(async () => { await hook.result.current.prepare(); });
    const original = Storage.prototype.setItem;
    const blocked = vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (
      this: Storage,
      key: string,
      value: string,
    ) {
      if (key.startsWith("yike.ui.operation.")) throw new Error("quota");
      return original.call(this, key, value);
    });
    await act(async () => { expect(await hook.result.current.confirm(true)).toBe(false); });
    expect(fake.api.confirm).not.toHaveBeenCalled();
    blocked.mockRestore();
    await act(async () => { expect(await hook.result.current.confirm(true)).toBe(true); });
    expect(fake.api.confirm).toHaveBeenCalledOnce();

    const revokeBlocked = vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (
      this: Storage,
      key: string,
      value: string,
    ) {
      if (key.startsWith("yike.ui.operation.")) throw new Error("quota");
      return original.call(this, key, value);
    });
    await act(async () => { expect(await hook.result.current.revoke()).toBe(false); });
    expect(fake.api.revoke).not.toHaveBeenCalled();
    revokeBlocked.mockRestore();
  });

  it("serializes two consumers so prepare, confirm, and revoke each POST only once", async () => {
    const { useStrategyConfirmation } = await implementation();
    const first = renderHook(() => useStrategyConfirmation(draft, limits));
    const second = renderHook(() => useStrategyConfirmation(draft, limits));
    await act(async () => {
      await Promise.all([first.result.current.prepare(), second.result.current.prepare()]);
    });
    expect(fake.api.prepare).toHaveBeenCalledOnce();
    await act(async () => { await second.result.current.reconcile(); });
    await act(async () => {
      await Promise.all([first.result.current.confirm(true), second.result.current.confirm(true)]);
    });
    expect(fake.api.confirm).toHaveBeenCalledOnce();
    await act(async () => {
      await Promise.all([first.result.current.revoke(), second.result.current.revoke()]);
    });
    expect(fake.api.revoke).toHaveBeenCalledOnce();
  });

  it("deactivates every same-scope consumer while another consumer revokes and after it settles", async () => {
    const { useStrategyConfirmation } = await implementation();
    const first = renderHook(() => useStrategyConfirmation(draft, limits));
    await act(async () => { await first.result.current.prepare(); });
    await act(async () => { await first.result.current.confirm(true); });
    const second = renderHook(() => useStrategyConfirmation(draft, limits));
    await act(async () => { await second.result.current.reconcile(); });
    expect(first.result.current.confirmed).toBe(true);

    let release!: () => void;
    const ordinary = fake.api.revoke.getMockImplementation()!;
    fake.api.revoke.mockImplementationOnce(request => new Promise(resolve => {
      release = () => { void ordinary(request).then(resolve); };
    }));
    let revoking!: Promise<boolean>;
    act(() => { revoking = second.result.current.revoke(); });
    await waitFor(() => expect(release).toBeTypeOf("function"));
    expect(first.result.current.pending).toBe(true);
    expect(first.result.current.confirmed).toBe(false);
    release();
    await act(async () => { expect(await revoking).toBe(true); });
    expect(first.result.current.pending).toBe(false);
    expect(first.result.current.confirmed).toBe(false);
  });

  it("rejects a delayed same-scope CONFIRMED recheck after another consumer starts revocation", async () => {
    const { useStrategyConfirmation } = await implementation();
    const first = renderHook(() => useStrategyConfirmation(draft, limits));
    await act(async () => { await first.result.current.prepare(); });
    await act(async () => { await first.result.current.confirm(true); });
    const second = renderHook(() => useStrategyConfirmation(draft, limits));
    await act(async () => { await second.result.current.reconcile(); });

    let releaseOld!: () => void;
    const ordinary = fake.api.getStrategy.getMockImplementation()!;
    fake.api.getStrategy.mockImplementationOnce(async id => {
      const oldConfirmed = await ordinary(id);
      return new Promise(resolve => { releaseOld = () => resolve(oldConfirmed); });
    });
    let checking!: Promise<boolean>;
    act(() => { checking = first.result.current.recheck(); });
    await waitFor(() => expect(releaseOld).toBeTypeOf("function"));
    await act(async () => { expect(await second.result.current.revoke()).toBe(true); });
    releaseOld();
    await act(async () => { expect(await checking).toBe(false); });
    expect(first.result.current.confirmed).toBe(false);
  });

  it("exposes a verified PREPARE receipt as read-only history when the changed draft cannot load a current view", async () => {
    const { useStrategyConfirmation } = await implementation();
    const hook = renderHook(() => useStrategyConfirmation(draft, limits));
    await act(async () => { await hook.result.current.prepare(); });
    const historical = hook.result.current.prepared!;
    draft = { ...draft, revision: draft.revision + 1, name: "", terms: [] };
    hook.rerender();
    fake.api.getStrategy.mockRejectedValueOnce(
      new ServiceError("SERVICE_UNAVAILABLE", "当前视图不可用", 503),
    );
    await act(async () => { expect(await hook.result.current.reconcile()).toBe(false); });
    const result = hook.result.current;
    expect(result.historyReceipt).toEqual(historical);
    expect(result.historyOnly).toBe(true);
    expect(result.prepared).toBeNull();
    expect(result.confirmed).toBe(false);
  });

  it("queries an unknown PREPARE first and restores an existing receipt without a second POST", async () => {
    const { useStrategyConfirmation } = await implementation();
    const ordinary = fake.api.prepare.getMockImplementation()!;
    fake.api.prepare.mockImplementationOnce(async request => {
      await ordinary(request);
      throw new ServiceError("SERVICE_TIMEOUT", "响应丢失");
    });
    const hook = renderHook(() => useStrategyConfirmation(draft, limits));
    await act(async () => { expect(await hook.result.current.prepare()).toBe(false); });
    const originalRequest = fake.api.prepare.mock.calls[0][0];
    await act(async () => { expect(await hook.result.current.retry()).toBe(true); });
    expect(fake.api.getReceipt).toHaveBeenCalledWith(originalRequest.request_id);
    expect(fake.api.prepare).toHaveBeenCalledOnce();
    expect(hook.result.current.pending).toBe(false);
    expect(hook.result.current.prepared).toEqual(
      fake.receipts.get(originalRequest.request_id),
    );
    expect(hook.result.current.confirmed).toBe(false);
  });

  it("retries an unknown PREPARE with the original UUID only after receipt lookup returns 404", async () => {
    const { useStrategyConfirmation } = await implementation();
    fake.api.prepare.mockRejectedValueOnce(new ServiceError("SERVICE_TIMEOUT", "超时"));
    const hook = renderHook(() => useStrategyConfirmation(draft, limits));
    await act(async () => { expect(await hook.result.current.prepare()).toBe(false); });
    const originalRequest = fake.api.prepare.mock.calls[0][0];
    await act(async () => { expect(await hook.result.current.retry()).toBe(true); });
    expect(fake.api.getReceipt).toHaveBeenCalledWith(originalRequest.request_id);
    expect(fake.api.prepare).toHaveBeenCalledTimes(2);
    expect(fake.api.prepare.mock.calls[1][0]).toEqual(originalRequest);
  });

  it.each([
    new ServiceError("SERVICE_UNAVAILABLE", "服务暂不可用", 503),
    new ServiceError("SERVICE_TIMEOUT", "核对超时"),
  ])("does not POST an unknown PREPARE when receipt lookup is inconclusive: %s", async lookupError => {
    const { useStrategyConfirmation } = await implementation();
    fake.api.prepare.mockRejectedValueOnce(new ServiceError("SERVICE_TIMEOUT", "超时"));
    const hook = renderHook(() => useStrategyConfirmation(draft, limits));
    await act(async () => { expect(await hook.result.current.prepare()).toBe(false); });
    fake.api.getReceipt.mockRejectedValueOnce(lookupError);
    await act(async () => { expect(await hook.result.current.retry()).toBe(false); });
    expect(fake.api.getReceipt).toHaveBeenCalledOnce();
    expect(fake.api.prepare).toHaveBeenCalledOnce();
    expect(hook.result.current.pending).toBe(true);
  });
});
