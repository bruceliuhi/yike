// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { TasksPage } from "../../src/renderer/pages/Tasks";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import type { AppContextValue } from "../../src/renderer/app/context";
import { parseRoute } from "../../src/renderer/domain/routes";
import { newTaskDraft, type TaskDraft } from "../../src/renderer/domain/models";
import type { YikeService } from "../../src/renderer/services/contracts";
let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
beforeEach(() => {
  clearLocalDrafts();
  context = {
    service: { tasks: vi.fn().mockResolvedValue([]) } as unknown as YikeService,
    session: { authenticated: true, userId: crypto.randomUUID() },
    route: parseRoute("#/collection"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
  };
});
afterEach(cleanup);
function seed(current: TaskDraft, saved: TaskDraft) {
  sessionStorage.setItem(
    "yike.ui.draft.v1.task." + context.session.userId,
    JSON.stringify(current),
  );
  sessionStorage.setItem(
    "yike.ui.draft.v1.task-library." + context.session.userId,
    JSON.stringify([saved]),
  );
}
function current() {
  return JSON.parse(
    sessionStorage.getItem("yike.ui.draft.v1.task." + context.session.userId)!,
  );
}
describe("继续编辑任务草稿", () => {
  it("保留同ID更高版本的本机编辑，并按最新运行方式返回", () => {
    const saved = {
      ...newTaskDraft(),
      name: "保存过的任务",
      revision: 1,
      savedAt: "2026-09-09T01:00:00Z",
    };
    const edited = {
      ...saved,
      name: "刚修改的监控任务",
      revision: 2,
      savedAt: null,
      mode: "monitor" as const,
      terms: [
        {
          id: "manual",
          value: "保留人工词",
          origin: "manual" as const,
          edited: false,
        },
      ],
    };
    seed(edited, saved);
    render(<TasksPage />);
    fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
    expect(current()).toEqual(edited);
    expect(context.navigate).toHaveBeenCalledWith("/tasks/new?mode=monitor");
  });
  it("打开不同ID时载入选中的保存草稿", () => {
    const saved = {
      ...newTaskDraft(),
      name: "选中的任务",
      revision: 1,
      savedAt: "2026-09-09T01:00:00Z",
    };
    const other = { ...newTaskDraft(), name: "另一个任务", revision: 8 };
    seed(other, saved);
    render(<TasksPage />);
    fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
    expect(current()).toEqual(saved);
  });
  it("同ID保存版本更高时不回退为旧本机版本", () => {
    const saved = {
      ...newTaskDraft(),
      name: "已保存新版本",
      revision: 3,
      savedAt: "2026-09-09T01:00:00Z",
    };
    seed({ ...saved, name: "旧版本", revision: 1 }, saved);
    render(<TasksPage />);
    fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
    expect(current()).toEqual(saved);
  });
});
