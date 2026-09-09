// @vitest-environment jsdom
import { StrictMode } from "react";
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearLocalDrafts, hasSessionContentAtRisk, hasUnsavedChanges, useLocalDraft } from "../../src/renderer/app/hooks";
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
    expect(hasSessionContentAtRisk()).toBe(true);
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


describe("window exit protects business content outside tasks", () => {
  it.each([
    ["materials.guest", [{id: "m1", name: "本机资料", text: "真实业务资料"}]],
    ["profile.guest", {fields: {service: "新服务"}, baseline: {service: "原服务"}}],
    ["contact-note:user:opp:v1", "待核对项目预算"],
    ["contact:user:opp", {comment: {content: "", savedContent: "原评论"}, dm: {content: "原私信", savedContent: "原私信"}}],
  ])("protects %s after its page unmounts", (name, initialValue) => {
    renderHook(useSessionDraftExitProtection);
    const draft = renderHook(() => useLocalDraft<unknown>(name, null, (value) => value === null || typeof value === typeof initialValue));
    act(() => draft.result.current[1](initialValue));
    draft.unmount();
    expect(hasUnsavedChanges()).toBe(false);
    expect(unload()).toBe(true);
    act(() => clearLocalDrafts());
    expect(unload()).toBe(false);
  });
  it("ignores untouched or synced business data and UI preferences", () => {
    renderHook(useSessionDraftExitProtection);
    sessionStorage.setItem(key("materials.empty"), "[]");
    sessionStorage.setItem(key("profile.synced"), JSON.stringify({fields: {service: "已同步"}, baseline: {service: "已同步"}}));
    sessionStorage.setItem(key("contact:synced"), JSON.stringify({comment: {content: "原评论", savedContent: "原评论"}, dm: {content: "", savedContent: ""}}));
    sessionStorage.setItem(key("contact-note:empty"), JSON.stringify("  "));
    sessionStorage.setItem(key("contact-list:user"), JSON.stringify({query: "查找", sort: "newest"}));
    expect(unload()).toBe(false);
  });
  it("protects restored material and memory-only notes when storage fails", () => {
    sessionStorage.setItem(key("materials.restored"), JSON.stringify([{id: "m", name: "原资料", text: "内容"}]));
    renderHook(useSessionDraftExitProtection);
    expect(unload()).toBe(true);
    act(() => clearLocalDrafts());
    const note = renderHook(() => useLocalDraft("contact-note:memory", ""));
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {throw new Error("quota");});
    act(() => note.result.current[1]("尚未同步的备注"));
    note.unmount();
    expect(unload()).toBe(true);
    act(() => clearLocalDrafts());
    expect(unload()).toBe(false);
  });
});


it("protects retained follow-up edits but not a merely opened correction", () => {
  renderHook(useSessionDraftExitProtection);
  const initial = {opportunityId: "o", status: "CONTACTED", note: "已登记", contact: "2026-09-10", nextStep: "", nextDate: "", ownerId: "u", reason: ""};
  const correction = renderHook(() => useLocalDraft("followup:v3:correction", initial));
  expect(unload()).toBe(false);
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {throw new Error("quota");});
  act(() => correction.result.current[1]({...initial, note: "改正的内容", reason: "修正"}));
  correction.unmount();
  expect(unload()).toBe(true);
  act(() => clearLocalDrafts());
  expect(unload()).toBe(false);
});
it("protects a previously retained follow-up after reload and clears its exit guard on submission", () => {
  renderHook(useSessionDraftExitProtection);
  const initial = {opportunityId: "o", status: "", note: "", contact: "", nextStep: "", nextDate: "", ownerId: "u", reason: ""};
  sessionStorage.setItem(key("followup:v3:restored"), JSON.stringify({...initial, note: "保留的跟进"}));
  const draft = renderHook(() => useLocalDraft("followup:v3:restored", initial));
  expect(unload()).toBe(true);
  act(() => draft.result.current[2]());
  expect(unload()).toBe(false);
});

it("stops warning when follow-up correction is restored to its initial server value", () => {
  renderHook(useSessionDraftExitProtection);
  const initial = {opportunityId: "o", status: "CONTACTED", note: "已登记", contact: "2026-09-10", nextStep: "", nextDate: "", ownerId: "u", reason: ""};
  const draft = renderHook(() => useLocalDraft("followup:v3:undo", initial));
  act(() => draft.result.current[1]({...initial, note: "临时改动"}));
  expect(unload()).toBe(true);
  vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {throw new Error("denied");});
  act(() => draft.result.current[1](initial));
  draft.unmount();
  expect(unload()).toBe(false);
});
