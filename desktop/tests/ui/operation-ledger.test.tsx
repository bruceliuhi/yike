// @vitest-environment jsdom
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook } from "@testing-library/react";
import { clearLocalDrafts, useLocalDraft } from "../../src/renderer/app/hooks";
import {
  operationLedgerKey,
  useOperationLedger,
} from "../../src/renderer/app/operationLedger";
import { newStrategyRecord, strategyRecordKey } from "../../src/renderer/domain/strategyConfirmation";
import type { PrepareStrategyRequest } from "../../src/shared/researchStrategies";
let user: string;
const pendingKey = JSON.stringify(["opportunity-id", "comment"]);
const sentKey = JSON.stringify(["opportunity-id", "comment", 1]);
const unknownTask = { "task-id": "task:task-id:1" };
beforeEach(() => {
  user = crypto.randomUUID();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
function stored(scope: "send-attempts" | "unknown-task-starts", id = user) {
  return JSON.parse(
    localStorage.getItem(operationLedgerKey(scope, id)) || "{}",
  );
}

describe("持久操作确认记录", () => {
  it("异步核对用捕获的只读getter同步看到最新锁，存储损坏时不读旧内存代替", () => {
    const a = renderHook(() => useOperationLedger("send-attempts", user));
    const b = renderHook(() => useOperationLedger("send-attempts", user));
    const latest = a.result.current[2];
    expect(latest).toBeTypeOf("function");
    const writes = vi.spyOn(Storage.prototype, "setItem");
    act(() => {
      b.result.current[1]({ [pendingKey]: "PENDING" });
      const beforeRead = writes.mock.calls.length;
      expect(latest!()).toEqual({ [pendingKey]: "PENDING" });
      expect(writes).toHaveBeenCalledTimes(beforeRead);
    });
    localStorage.setItem(operationLedgerKey("send-attempts", user), "{broken");
    expect(() => latest!()).toThrow("操作确认记录");
  });

  it("策略原请求先可靠保存，清草稿后仍保留且拒绝正文混入", async () => {
    const request: PrepareStrategyRequest = { schema_version: "strategy-confirmation-v1", request_id: crypto.randomUUID(),
      draft_id: crypto.randomUUID(), draft_revision: 1, profile_version_id: crypto.randomUUID(),
      configuration: { schema_version: "research-strategy-v1", name: "私有业务原文", source: "search", keywords: ["设备采购"],
        exclusions: [], links: [], mode: "once", schedule: null, research: null },
      platforms: ["PUBLIC_WEB"], max_records: 10, max_runtime_seconds: 600 };
    const record = await newStrategyRecord(request, { userId: user, accountScopeId: null, scopeVersion: null, fingerprint: "a".repeat(64) });
    const scope = "research-strategy-operations" as Parameters<typeof useOperationLedger>[0];
    const view = renderHook(() => useOperationLedger(scope, user));
    const key = strategyRecordKey(record);
    act(() => view.result.current[1]({ [key]: JSON.stringify(record) }));
    act(() => clearLocalDrafts());
    expect(view.result.current[0][key]).toBe(JSON.stringify(record));
    expect(localStorage.getItem(operationLedgerKey(scope, user))).not.toContain(request.configuration.name);
    expect(() => view.result.current[1]({ [key]: JSON.stringify({ ...record, token: "private" }) })).toThrow();
    expect(() => view.result.current[1]({ [key]: JSON.stringify({ ...record, context: { ...record.context, userId: crypto.randomUUID() } }) })).toThrow();
  });
  it("清除编辑草稿不清除未知发送或启动记录", () => {
    const send = renderHook(() => useOperationLedger("send-attempts", user));
    const task = renderHook(() =>
      useOperationLedger("unknown-task-starts", user),
    );
    act(() => {
      send.result.current[1]({ [pendingKey]: "PENDING" });
      task.result.current[1](unknownTask);
    });
    sessionStorage.setItem(
      "yike.ui.draft.v1.contact:editable",
      "synthetic draft text",
    );
    act(() => clearLocalDrafts());
    expect(
      sessionStorage.getItem("yike.ui.draft.v1.contact:editable"),
    ).toBeNull();
    expect(send.result.current[0]).toEqual({ [pendingKey]: "PENDING" });
    expect(task.result.current[0]).toEqual(unknownTask);
    expect(stored("send-attempts")).toEqual({ [pendingKey]: "PENDING" });
    expect(stored("unknown-task-starts")).toEqual(unknownTask);
  });
  it("退出与重新挂载后从localStorage恢复同一账号的锁", () => {
    const view = renderHook(() => useOperationLedger("send-attempts", user));
    act(() => view.result.current[1]({ [pendingKey]: "PENDING" }));
    view.unmount();
    act(() => clearLocalDrafts());
    sessionStorage.clear();
    const next = renderHook(() => useOperationLedger("send-attempts", user));
    expect(next.result.current[0]).toEqual({ [pendingKey]: "PENDING" });
  });
  it("切换用户及访客不会显示前一账号的记录，同用户重登仍有锁", () => {
    const view = renderHook(
      ({ id }: { id?: string }) => useOperationLedger("send-attempts", id),
      { initialProps: { id: user as string | undefined } },
    );
    act(() => view.result.current[1]({ [pendingKey]: "PENDING" }));
    view.rerender({ id: undefined });
    expect(view.result.current[0]).toEqual({});
    view.rerender({ id: "other-" + user });
    expect(view.result.current[0]).toEqual({});
    view.rerender({ id: user });
    expect(view.result.current[0]).toEqual({ [pendingKey]: "PENDING" });
  });
  it("账号切换后迟到的确认结果只更新原账号", () => {
    const view = renderHook(
      ({ id }) => useOperationLedger("send-attempts", id),
      { initialProps: { id: user } },
    );
    act(() => view.result.current[1]({ [pendingKey]: "PENDING" }));
    const settle = view.result.current[1];
    view.rerender({ id: "other-" + user });
    act(() => settle({ [sentKey]: "SENT" }));
    expect(view.result.current[0]).toEqual({});
    expect(stored("send-attempts")).toEqual({ [sentKey]: "SENT" });
    expect(stored("send-attempts", "other-" + user)).toEqual({});
  });
  it("离开页面后仍能持久化已开始操作的最终结果", () => {
    const view = renderHook(() =>
      useOperationLedger("unknown-task-starts", user),
    );
    act(() => view.result.current[1](unknownTask));
    const settle = view.result.current[1];
    view.unmount();
    act(() => settle({}));
    expect(stored("unknown-task-starts")).toEqual({});
  });
  it("首次迁移前清草稿也保留旧sessionStorage锁", () => {
    const sendOld = "yike.ui.draft.v1.send-attempts." + user;
    const taskOld = "yike.ui.draft.v1.unknown-task-starts." + user;
    sessionStorage.setItem(
      sendOld,
      JSON.stringify({ [pendingKey]: "PENDING" }),
    );
    sessionStorage.setItem(taskOld, JSON.stringify(unknownTask));
    clearLocalDrafts();
    expect(sessionStorage.getItem(sendOld)).not.toBeNull();
    expect(sessionStorage.getItem(taskOld)).not.toBeNull();
    const send = renderHook(() => useOperationLedger("send-attempts", user));
    const task = renderHook(() =>
      useOperationLedger("unknown-task-starts", user),
    );
    expect(send.result.current[0]).toEqual({ [pendingKey]: "PENDING" });
    expect(task.result.current[0]).toEqual(unknownTask);
    expect(sessionStorage.getItem(sendOld)).toBeNull();
    expect(sessionStorage.getItem(taskOld)).toBeNull();
  });
  it("合并旧锁与现有持久记录，不覆盖已经确认的版本记录", () => {
    localStorage.setItem(
      operationLedgerKey("send-attempts", user),
      JSON.stringify({ [sentKey]: "SENT" }),
    );
    sessionStorage.setItem(
      "yike.ui.draft.v1.send-attempts." + user,
      JSON.stringify({ [pendingKey]: "PENDING" }),
    );
    const view = renderHook(() => useOperationLedger("send-attempts", user));
    expect(view.result.current[0]).toEqual({
      [pendingKey]: "PENDING",
      [sentKey]: "SENT",
    });
  });
  it("迁移写入失败时保留旧锁，并阻止新的外部提交", () => {
    const legacy = "yike.ui.draft.v1.unknown-task-starts." + user;
    sessionStorage.setItem(legacy, JSON.stringify(unknownTask));
    const original = Storage.prototype.setItem;
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (
      this: Storage,
      key,
      value,
    ) {
      if (this === localStorage)
        throw new DOMException("denied", "QuotaExceededError");
      return original.call(this, key, value);
    });
    const view = renderHook(() =>
      useOperationLedger("unknown-task-starts", user),
    );
    const submit = vi.fn();
    expect(view.result.current[0]).toEqual(unknownTask);
    expect(() => {
      view.result.current[1]({ "new-id": "task:new-id:1" });
      submit();
    }).toThrow("操作确认记录");
    expect(submit).not.toHaveBeenCalled();
    expect(sessionStorage.getItem(legacy)).not.toBeNull();
  });
  it("持久记录损坏时不静默置空后允许重复提交", () => {
    localStorage.setItem(operationLedgerKey("send-attempts", user), "{broken");
    const view = renderHook(() => useOperationLedger("send-attempts", user));
    const submit = vi.fn();
    expect(() => {
      view.result.current[1]({ [pendingKey]: "PENDING" });
      submit();
    }).toThrow("操作确认记录");
    expect(submit).not.toHaveBeenCalled();
    expect(
      localStorage.getItem(operationLedgerKey("send-attempts", user)),
    ).toBe("{broken");
  });
  it("新锁不能可靠写入时停止外部提交，不假装已记录", () => {
    const view = renderHook(() => useOperationLedger("send-attempts", user));
    const original = Storage.prototype.setItem;
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (
      this: Storage,
      key,
      value,
    ) {
      if (this === localStorage)
        throw new DOMException("denied", "QuotaExceededError");
      return original.call(this, key, value);
    });
    const submit = vi.fn();
    expect(() => {
      view.result.current[1]({ [pendingKey]: "PENDING" });
      submit();
    }).toThrow("操作确认记录");
    expect(submit).not.toHaveBeenCalled();
    expect(view.result.current[0]).toEqual({});
  });
  it("只接受标识符和预期状态，不允许保存正文或凭证字段", () => {
    const view = renderHook(() => useOperationLedger("send-attempts", user));
    expect(() =>
      view.result.current[1]({
        content: "private draft text",
        token: "private token",
      }),
    ).toThrow("操作确认记录");
    expect(
      localStorage.getItem(operationLedgerKey("send-attempts", user)),
    ).toBeNull();
  });
  it("StrictMode下同域多个消费者同步看到已经写入的锁", () => {
    const a = renderHook(() => useOperationLedger("send-attempts", user), {
      wrapper: StrictMode,
    });
    const b = renderHook(() => useOperationLedger("send-attempts", user), {
      wrapper: StrictMode,
    });
    act(() => a.result.current[1]({ [pendingKey]: "PENDING" }));
    expect(b.result.current[0]).toEqual({ [pendingKey]: "PENDING" });
  });
  it("旧版本仅保存在内存中的锁也在清草稿后迁移", () => {
    const key = "send-attempts." + user;
    const legacy = renderHook(() =>
      useLocalDraft<Record<string, string>>(key, {}, () => true),
    );
    const original = Storage.prototype.setItem;
    const writing = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(function (this: Storage, name, value) {
        if (this === sessionStorage)
          throw new DOMException("denied", "QuotaExceededError");
        return original.call(this, name, value);
      });
    act(() => legacy.result.current[1]({ [pendingKey]: "PENDING" }));
    legacy.unmount();
    writing.mockRestore();
    act(() => clearLocalDrafts());
    const migrated = renderHook(() =>
      useOperationLedger("send-attempts", user),
    );
    expect(migrated.result.current[0]).toEqual({ [pendingKey]: "PENDING" });
    expect(stored("send-attempts")).toEqual({ [pendingKey]: "PENDING" });
  });
});
