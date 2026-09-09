// @vitest-environment jsdom
import { StrictMode } from "react";
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearLocalDrafts, hasSessionTaskDrafts, hasUnsavedChanges, useLocalDraft } from "../../src/renderer/app/hooks";
import { useSessionDraftExitProtection } from "../../src/renderer/app/sessionDraftExit";
import { newTaskDraft } from "../../src/renderer/domain/models";

const key = (name: string) => "yike.ui.draft.v1." + name;
function unload() {
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  return event.defaultPrevented;
}
beforeEach(() => { clearLocalDrafts(); sessionStorage.clear(); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); clearLocalDrafts(); });

describe("window exit protects ephemeral task work", () => {
  it("does not prompt for opening an empty task or for unrelated view preferences", () => {
    renderHook(useSessionDraftExitProtection);
    renderHook(() => useLocalDraft("task.empty", () => newTaskDraft("monitor")));
    sessionStorage.setItem(key("outreach-view.a"), JSON.stringify({ query: "name" }));
    expect(unload()).toBe(false);
  });
  it("protects the most recent edit synchronously without blocking internal navigation", () => {
    renderHook(useSessionDraftExitProtection);
    const draft = renderHook(() => useLocalDraft("task.guest", () => newTaskDraft()));
    act(() => {
      draft.result.current[1]((old) => ({ ...old, name: "未同步的任务" }));
      expect(unload()).toBe(true);
    });
    expect(hasUnsavedChanges()).toBe(false);
    draft.unmount();
    expect(unload()).toBe(true);
  });
  it("protects a saved task library even after the editor leaves and a window reloads", () => {
    sessionStorage.setItem(key("task-library.user-a"), JSON.stringify([
      { ...newTaskDraft(), name: "已保存的会话草稿", savedAt: "2026-09-09T10:00:00Z" },
    ]));
    renderHook(useSessionDraftExitProtection);
    expect(hasSessionTaskDrafts()).toBe(true);
    expect(unload()).toBe(true);
  });
  it("treats saved templates as session content but not durable unknown-operation ledgers", () => {
    renderHook(useSessionDraftExitProtection);
    sessionStorage.setItem(key("unknown-task-starts.a"), JSON.stringify({ id: "pending" }));
    expect(unload()).toBe(false);
    sessionStorage.setItem(key("task-templates.a"), JSON.stringify([{ id: "template-a" }]));
    expect(unload()).toBe(true);
  });
  it("protects condition-only edits even when the name remains blank", () => {
    renderHook(useSessionDraftExitProtection);
    const draft = renderHook(() => useLocalDraft("task.a", () => newTaskDraft()));
    act(() => draft.result.current[1]((old) => ({ ...old, revision: old.revision + 1 })));
    expect(unload()).toBe(true);
  });
  it("clears exit protection when all local task content is deliberately cleared", () => {
    renderHook(useSessionDraftExitProtection);
    const a = renderHook(() => useLocalDraft("task.a", () => newTaskDraft()));
    const b = renderHook(() => useLocalDraft("task.b", () => newTaskDraft()));
    act(() => { a.result.current[1]((old) => ({ ...old, name: "A" })); b.result.current[1]((old) => ({ ...old, name: "B" })); });
    act(() => a.result.current[2]());
    expect(unload()).toBe(true);
    act(() => clearLocalDrafts());
    expect(unload()).toBe(false);
  });
  it("does not resurrect cleared content when storage removal fails", () => {
    renderHook(useSessionDraftExitProtection);
    sessionStorage.setItem(key("task.denied-removal"), JSON.stringify({ ...newTaskDraft(), name: "A" }));
    expect(unload()).toBe(true);
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => { throw new Error("denied"); });
    act(() => clearLocalDrafts());
    expect(unload()).toBe(false);
  });
  it("still protects memory-only edits if session storage is unavailable", () => {
    renderHook(useSessionDraftExitProtection);
    const draft = renderHook(() => useLocalDraft("task.a", () => newTaskDraft()));
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota"); });
    act(() => draft.result.current[1]((old) => ({ ...old, name: "内存草稿" })));
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("denied"); });
    expect(unload()).toBe(true);
  });
  it("ignores malformed stored JSON and cleans up its StrictMode listener", () => {
    sessionStorage.setItem(key("task.malformed"), "{bad");
    const guard = renderHook(useSessionDraftExitProtection, { wrapper: StrictMode });
    expect(unload()).toBe(false);
    sessionStorage.setItem(key("task.malformed"), JSON.stringify({ ...newTaskDraft(), name: "A" }));
    expect(unload()).toBe(true);
    guard.unmount();
    expect(unload()).toBe(false);
  });
});
