// @vitest-environment jsdom
import { StrictMode } from "react";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearLocalDrafts,
  useLocalDraft,
  useResource,
} from "../../src/renderer/app/hooks";

const storageKey = (key: string) => "yike.ui.draft.v1." + key;
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
beforeEach(() => {
  clearLocalDrafts();
  sessionStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  clearLocalDrafts();
});

describe("persistent draft recovery and ownership", () => {
  it("discards malformed JSON without writing defaults back to storage", () => {
    sessionStorage.setItem(storageKey("bad-json"), "{bad");
    const { result } = renderHook(() =>
      useLocalDraft("bad-json", { text: "" }),
    );
    expect(result.current[0]).toEqual({ text: "" });
    expect(sessionStorage.getItem(storageKey("bad-json"))).toBeNull();
  });
  it("rejects deeply wrong fields and object values in nullable scalar fields", () => {
    sessionStorage.setItem(
      storageKey("nested"),
      JSON.stringify({
        fields: { service: 42 },
        baseline: { service: "" },
        versionId: { bad: true },
      }),
    );
    const initial = {
      fields: { service: "" },
      baseline: { service: "" },
      versionId: null as string | null,
    };
    const { result } = renderHook(() => useLocalDraft("nested", initial));
    expect(result.current[0]).toEqual(initial);
    expect(sessionStorage.getItem(storageKey("nested"))).toBeNull();
  });
  it("restores valid nested values and a nullable scalar identifier", () => {
    const saved = {
      fields: { service: "设计" },
      baseline: { service: "" },
      versionId: "version-2",
    };
    sessionStorage.setItem(storageKey("profile"), JSON.stringify(saved));
    const { result } = renderHook(() =>
      useLocalDraft("profile", {
        fields: { service: "" },
        baseline: { service: "" },
        versionId: null as string | null,
      }),
    );
    expect(result.current[0]).toEqual(saved);
  });
  it("preserves edits that explicitly clear an optional object field", () => {
    const { result } = renderHook(() =>
      useLocalDraft<{ text: string; confirmation?: string }>("optional", {
        text: "",
      }),
    );
    act(() =>
      result.current[1]({ text: "manual edit", confirmation: undefined }),
    );
    expect(result.current[0].text).toBe("manual edit");
    expect(JSON.parse(sessionStorage.getItem(storageKey("optional"))!)).toEqual(
      { text: "manual edit" },
    );
  });
  it("requires an element validator for nonempty arrays with an empty default", () => {
    sessionStorage.setItem(storageKey("unknown-list"), "[{}]");
    const fallback = renderHook(() =>
      useLocalDraft("unknown-list", [] as { id: string }[]),
    );
    expect(fallback.result.current[0]).toEqual([]);
    sessionStorage.setItem(storageKey("known-list"), '[{"id":"material-a"}]');
    const known = renderHook(() =>
      useLocalDraft(
        "known-list",
        [] as { id: string }[],
        (value) =>
          Array.isArray(value) &&
          value.every((item) => item && typeof item.id === "string"),
      ),
    );
    expect(known.result.current[0]).toEqual([{ id: "material-a" }]);
  });
  it("contains validator exceptions and restores the initial draft", () => {
    sessionStorage.setItem(storageKey("throws"), "{}");
    const { result } = renderHook(() =>
      useLocalDraft("throws", { text: "" }, () => {
        throw new Error("bad schema input");
      }),
    );
    expect(result.current[0]).toEqual({ text: "" });
  });
  it("switches accounts immediately and ignores a captured setter from the old account", () => {
    const { result, rerender } = renderHook(
      ({ user }) => useLocalDraft(user, { text: "" }),
      { initialProps: { user: "user-a" } },
    );
    act(() => result.current[1]({ text: "A private text" }));
    const oldSetter = result.current[1];
    rerender({ user: "user-b" });
    expect(result.current[0]).toEqual({ text: "" });
    act(() => oldSetter({ text: "late A response" }));
    expect(result.current[0]).toEqual({ text: "" });
    act(() => result.current[1]({ text: "B private text" }));
    rerender({ user: "user-a" });
    expect(result.current[0]).toEqual({ text: "A private text" });
    expect(JSON.parse(sessionStorage.getItem(storageKey("user-b"))!)).toEqual({
      text: "B private text",
    });
  });
  it("clear updates mounted consumers immediately and rejects delayed old writes", () => {
    const { result, rerender } = renderHook(() =>
      useLocalDraft("clear-all", { text: "" }),
    );
    act(() => result.current[1]({ text: "private" }));
    const oldSetter = result.current[1];
    act(() => clearLocalDrafts());
    expect(result.current[0]).toEqual({ text: "" });
    act(() => oldSetter({ text: "late save" }));
    rerender();
    expect(result.current[0]).toEqual({ text: "" });
    expect(sessionStorage.getItem(storageKey("clear-all"))).toBeNull();
    act(() => result.current[1]({ text: "new deliberate edit" }));
    expect(result.current[0].text).toBe("new deliberate edit");
  });
  it("per-key clear preserves other drafts and does not persist the reset value", () => {
    const a = renderHook(() => useLocalDraft("a", { text: "" }));
    const b = renderHook(() => useLocalDraft("b", { text: "" }));
    act(() => {
      a.result.current[1]({ text: "A" });
      b.result.current[1]({ text: "B" });
    });
    const old = a.result.current[1];
    act(() => a.result.current[2]());
    act(() => old({ text: "stale" }));
    expect(a.result.current[0]).toEqual({ text: "" });
    expect(b.result.current[0]).toEqual({ text: "B" });
    expect(sessionStorage.getItem(storageKey("a"))).toBeNull();
  });
  it("does not reload a cleared private value when storage removal is denied", () => {
    const { result } = renderHook(() =>
      useLocalDraft("denied-clear", { text: "" }),
    );
    act(() => result.current[1]({ text: "private" }));
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    act(() => clearLocalDrafts());
    expect(result.current[0]).toEqual({ text: "" });
    expect(sessionStorage.getItem(storageKey("denied-clear"))).toContain(
      "private",
    );
    act(() => result.current[1]({ text: "new edit" }));
    expect(result.current[0]).toEqual({ text: "new edit" });
  });
  it("survives StrictMode and runs a functional edit once", () => {
    const updater = vi.fn((old: { count: number }) => ({
      count: old.count + 1,
    }));
    const { result } = renderHook(() => useLocalDraft("strict", { count: 0 }), {
      wrapper: StrictMode,
    });
    act(() => result.current[1](updater));
    expect(result.current[0].count).toBe(1);
    expect(updater).toHaveBeenCalledTimes(1);
    act(() => clearLocalDrafts());
    expect(result.current[0].count).toBe(0);
    expect(sessionStorage.getItem(storageKey("strict"))).toBeNull();
  });
  it("keeps valid edits in memory when browser storage rejects reads or writes", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("full", "QuotaExceededError");
    });
    const first = renderHook(() => useLocalDraft("memory", { text: "" }));
    act(() => first.result.current[1]({ text: "retained" }));
    first.unmount();
    const second = renderHook(() => useLocalDraft("memory", { text: "" }));
    expect(second.result.current[0].text).toBe("retained");
  });
});

describe("resource identity and late results", () => {
  it("ends an unbounded read, aborts it, and ignores its late response after retry", async () => {
    vi.useFakeTimers();
    const old = deferred<string>();
    let signal: AbortSignal | undefined;
    const loader = vi.fn().mockImplementationOnce((value?: AbortSignal) => { signal = value; return old.promise; }).mockResolvedValueOnce("fresh");
    const { result } = renderHook(() => useResource<string>(loader));
    await act(async () => { await vi.advanceTimersByTimeAsync(31_001); });
    expect(result.current.error).toBe("读取超时，请重试。");
    expect(result.current.loading).toBe(false); expect(signal?.aborted).toBe(true);
    await act(async () => { await result.current.reload(); });
    await act(async () => old.resolve("late"));
    expect(result.current.data).toBe("fresh");
  });
  it("never renders the previous account data while the next account loads or fails", async () => {
    const next = deferred<string>();
    const loader = vi.fn((id: string) =>
      id === "a" ? Promise.resolve("A private data") : next.promise,
    );
    const { result, rerender } = renderHook(
      ({ user }) => useResource(() => loader(user), [user]),
      { initialProps: { user: "a" } },
    );
    await waitFor(() => expect(result.current.data).toBe("A private data"));
    rerender({ user: "b" });
    expect(result.current.data).toBeUndefined();
    expect(result.current.loading).toBe(true);
    await act(async () => next.reject(new Error("当前账号暂不可用")));
    expect(result.current.data).toBeUndefined();
    expect(result.current.error).toBe("当前账号暂不可用");
    expect(result.current.loading).toBe(false);
  });
  it("discards an old identity result even when it resolves last", async () => {
    const a = deferred<string>();
    const b = deferred<string>();
    const { result, rerender } = renderHook(
      ({ user }) =>
        useResource(() => (user === "a" ? a.promise : b.promise), [user]),
      { initialProps: { user: "a" } },
    );
    rerender({ user: "b" });
    await act(async () => b.resolve("B"));
    await act(async () => a.resolve("A"));
    expect(result.current.data).toBe("B");
  });
  it("clears old results on failed reload and ignores overlapping older reloads", async () => {
    const second = deferred<string>();
    const third = deferred<string>();
    const loader = vi
      .fn()
      .mockResolvedValueOnce("initial")
      .mockImplementationOnce(() => second.promise)
      .mockImplementationOnce(() => third.promise);
    const { result } = renderHook(() => useResource<string>(loader, []));
    await waitFor(() => expect(result.current.data).toBe("initial"));
    act(() => {
      void result.current.reload();
    });
    expect(result.current.data).toBeUndefined();
    act(() => {
      void result.current.reload();
    });
    await act(async () => third.reject(new Error("最新读取未完成")));
    await act(async () => second.resolve("stale"));
    expect(result.current.data).toBeUndefined();
    expect(result.current.error).toBe("最新读取未完成");
  });
  it("preserves a newer explicit update against an older pending fetch", async () => {
    const pending = deferred<string>();
    const { result } = renderHook(() => useResource(() => pending.promise, []));
    act(() => result.current.setData("new saved result"));
    await act(async () => pending.resolve("old fetch"));
    expect(result.current.data).toBe("new saved result");
    expect(result.current.loading).toBe(false);
  });
  it("uses only the active StrictMode request result", async () => {
    const old = deferred<string>();
    const active = deferred<string>();
    const loader = vi
      .fn()
      .mockImplementationOnce(() => old.promise)
      .mockImplementation(() => active.promise);
    const { result } = renderHook(() => useResource<string>(loader, []), {
      wrapper: StrictMode,
    });
    await act(async () => active.resolve("active"));
    await act(async () => old.resolve("old"));
    expect(result.current.data).toBe("active");
  });
});
