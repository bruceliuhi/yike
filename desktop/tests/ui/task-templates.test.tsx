// @vitest-environment jsdom
import { beforeEach, afterEach, it, expect, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { TasksPage } from "../../src/renderer/pages/Tasks";
import { TaskDraftRow } from "../../src/renderer/pages/tasks/TaskDraftRow";
import {
  templateFromDraft,
  draftFromTemplate,
} from "../../src/renderer/pages/tasks/localTemplates";
import { taskDraftSchema } from "../../src/renderer/app/taskDraft";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { operationLedgerKey } from "../../src/renderer/app/operationLedger";
import { newTaskDraft, type TaskDraft } from "../../src/renderer/domain/models";
import type { AppContextValue } from "../../src/renderer/app/context";
import type { YikeService } from "../../src/renderer/services/contracts";
import { parseRoute } from "../../src/renderer/domain/routes";
let context: AppContextValue;
let draft: TaskDraft;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
const dataKey = (name: string) =>
  `yike.ui.draft.v1.${name}.${context.session.userId}`;
const templates = () =>
  JSON.parse(sessionStorage.getItem(dataKey("task-templates")) || "[]");
function pending(id: string) {
  localStorage.setItem(
    operationLedgerKey("unknown-task-starts", context.session.userId!),
    JSON.stringify({ [id]: `task:${id}:1` }),
  );
}
beforeEach(() => {
  clearLocalDrafts();
  sessionStorage.clear();
  localStorage.clear();
  context = {
    service: {
      tasks: vi.fn().mockResolvedValue([]),
      startTask: vi.fn(),
      taskAction: vi.fn(),
    } as unknown as YikeService,
    session: { authenticated: true, userId: crypto.randomUUID() },
    sessionReady: true,
    route: parseRoute("#/collection"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
  };
  draft = {
    ...newTaskDraft(),
    name: "TEST用户条件",
    profileId: "profile",
    profileVersion: 2,
    terms: [{ id: "t1", value: "人工精修词", origin: "manual", edited: true }],
    exclusions: [{ id: "e1", value: "招聘", origin: "manual", edited: true }],
    platforms: ["xhs", "douyin", "bilibili", "zhihu", "web"],
    accounts: { xhs: "account" },
    savedAt: "2026-09-09T00:00:00Z",
  };
  sessionStorage.setItem(dataKey("task-library"), JSON.stringify([draft]));
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
async function saveTemplate(name = "TEST独立模板") {
  fireEvent.click(await screen.findByRole("button", { name: "保存为模板" }));
  fireEvent.change(screen.getByRole("textbox", { name: "模板名称" }), {
    target: { value: name },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存模板" }));
  await screen.findByText(name);
}
it("saves a named standalone template and creates a new draft with only user configuration", async () => {
  const view = render(<TasksPage />);
  await saveTemplate();
  expect(templates()).toHaveLength(1);
  expect(screen.getByText("本机会话模板 · 未同步")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "从模板新建" }));
  const created = JSON.parse(sessionStorage.getItem(dataKey("task"))!);
  expect(created.id).not.toBe(draft.id);
  expect(created.revision).toBe(1);
  expect(created.savedAt).toBeNull();
  expect(created.terms).toEqual(draft.terms);
  expect(created.accounts).toEqual(draft.accounts);
  expect(created.templateSourceDraftIds).toEqual([draft.id]);
  expect(context.service.startTask).not.toHaveBeenCalled();
  expect(context.navigate).toHaveBeenCalledWith("/tasks/new");
  view.unmount();
  render(<TasksPage />);
  expect(await screen.findByText("TEST独立模板")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "删除模板" }));
  fireEvent.click(
    within(screen.getByRole("dialog", { name: "删除本机模板？" })).getByRole(
      "button",
      { name: "删除模板" },
    ),
  );
  expect(templates()).toEqual([]);
  expect(screen.getByText("TEST用户条件")).toBeTruthy();
});
it("strips runtime fields and propagates ancestor source IDs across template generations", () => {
  const first = templateFromDraft(
    {
      ...draft,
      status: "RUNNING",
      requestId: "must-not-copy",
      result: { count: 123 },
    } as TaskDraft,
    "一代",
  );
  const child = draftFromTemplate(first);
  const second = templateFromDraft(child, "二代");
  const third = draftFromTemplate(second);
  expect(third.templateSourceDraftIds).toEqual([draft.id, child.id]);
  expect(third.id).not.toBe(child.id);
  expect(third).not.toHaveProperty("status");
  expect(third).not.toHaveProperty("requestId");
  expect(third).not.toHaveProperty("result");
  expect(second.conditions).not.toHaveProperty("id");
  expect(second.conditions).not.toHaveProperty("templateSourceDraftIds");
});
it("refuses saving when the source becomes unresolved after naming opens, even without a storage event", async () => {
  render(<TasksPage />);
  fireEvent.click(await screen.findByRole("button", { name: "保存为模板" }));
  pending(draft.id);
  fireEvent.click(screen.getByRole("button", { name: "保存模板" }));
  await screen.findByText(/源草稿或其模板来源有启动结果待核对/);
  expect(templates()).toEqual([]);
});
it("refuses using a pre-existing template if any ancestor later becomes unresolved", async () => {
  const child = draftFromTemplate(templateFromDraft(draft, "一代"));
  const second = templateFromDraft(child, "二代");
  sessionStorage.setItem(dataKey("task-templates"), JSON.stringify([second]));
  render(<TasksPage />);
  await screen.findByRole("button", { name: "从模板新建" });
  pending(draft.id);
  fireEvent.click(screen.getByRole("button", { name: "从模板新建" }));
  await screen.findByText(/源草稿或其模板来源有启动结果待核对/);
  expect(context.navigate).not.toHaveBeenCalled();
  expect(context.service.startTask).not.toHaveBeenCalled();
});
it("does not clone if unknown-result storage cannot be verified", async () => {
  render(<TasksPage />);
  await saveTemplate();
  const original = Storage.prototype.getItem;
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (
    this: Storage,
    key,
  ) {
    if (key.startsWith("yike.ui.operation.")) throw new Error("storage denied");
    return original.call(this, key);
  });
  fireEvent.click(screen.getByRole("button", { name: "从模板新建" }));
  await screen.findByText(/操作确认记录暂时无法可靠保存/);
  expect(context.navigate).not.toHaveBeenCalled();
});
it("clears session templates with local drafts and isolates them from another identity", async () => {
  const view = render(<TasksPage />);
  await saveTemplate();
  const user = context.session.userId;
  context = {
    ...context,
    session: { authenticated: true, userId: "other-user" },
  };
  view.rerender(<TasksPage />);
  expect(screen.queryByText("TEST独立模板")).toBeNull();
  context = { ...context, session: { authenticated: true, userId: user } };
  view.rerender(<TasksPage />);
  expect(screen.getByText("TEST独立模板")).toBeTruthy();
  act(() => clearLocalDrafts());
  expect(screen.queryByText("TEST独立模板")).toBeNull();
  expect(templates()).toEqual([]);
});
it("validates bounded unique nonempty template ancestry while accepting legacy drafts", () => {
  expect(taskDraftSchema.safeParse(draft).success).toBe(true);
  expect(
    taskDraftSchema.safeParse({
      ...draft,
      templateSourceDraftIds: ["ancestor"],
    }).success,
  ).toBe(true);
  for (const ids of [
    ["same", "same"],
    ["   "],
    [""],
    Array.from({ length: 51 }, (_, i) => String(i)),
  ])
    expect(
      taskDraftSchema.safeParse({ ...draft, templateSourceDraftIds: ids })
        .success,
    ).toBe(false);
});
it("expands monitor configuration read-only, shows every platform and does not invent run history", () => {
  const confirm = vi.fn();
  render(
    <TaskDraftRow
      draft={{
        ...draft,
        mode: "monitor",
        schedule: {
          kind: "interval",
          interval: 3,
          times: [],
          start: "09:00",
          end: "18:00",
          timezone: "Asia/Shanghai",
        },
      }}
      pending={false}
      onEdit={vi.fn()}
      onDelete={vi.fn()}
      onConfirm={confirm}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "查看配置" }));
  const panel = within(screen.getByRole("region", { name: "监控草稿配置" }));
  expect(panel.getByText("人工精修词")).toBeTruthy();
  for (const name of ["小红书", "抖音", "B站", "知乎", "公开网站"])
    expect(panel.getByText(name)).toBeTruthy();
  expect(panel.getByText("每 3 小时 · 09:00–18:00")).toBeTruthy();
  expect(panel.getByText("Asia/Shanghai")).toBeTruthy();
  expect(panel.queryByText("最近运行")).toBeNull();
  expect(panel.queryByText("下次计划")).toBeNull();
  expect(panel.queryByRole("textbox")).toBeNull();
  fireEvent.click(panel.getByRole("button", { name: "前往确认启动" }));
  expect(confirm).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "收起配置" }));
  expect(screen.queryByRole("region", { name: "监控草稿配置" })).toBeNull();
});
it("keeps unresolved monitor expansion inspectable while blocking confirmation", () => {
  const confirm = vi.fn();
  render(
    <TaskDraftRow
      draft={{ ...draft, mode: "monitor" }}
      pending
      onEdit={vi.fn()}
      onDelete={vi.fn()}
      onConfirm={confirm}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "查看配置" }));
  const button = screen.getByRole("button", {
    name: "前往确认启动",
  }) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  fireEvent.click(button);
  expect(confirm).not.toHaveBeenCalled();
  expect(screen.getByText("原启动结果待核对")).toBeTruthy();
});
it("opens a saved monitor at the existing final confirmation route without starting", async () => {
  context.route = parseRoute("#/monitors");
  sessionStorage.setItem(
    dataKey("task-library"),
    JSON.stringify([{ ...draft, mode: "monitor" }]),
  );
  render(<TasksPage />);
  fireEvent.click(await screen.findByRole("button", { name: "查看配置" }));
  fireEvent.click(screen.getByRole("button", { name: "前往确认启动" }));
  expect(context.navigate).toHaveBeenCalledWith(
    "/tasks/new?mode=monitor&step=confirm",
  );
  expect(context.service.startTask).not.toHaveBeenCalled();
});
it('disables an open deletion confirmation when an ancestor becomes unresolved', async () => {
  const derived = {...draft, templateSourceDraftIds:['ancestor-original']};
  sessionStorage.setItem(dataKey('task-library'), JSON.stringify([derived]));
  render(<TasksPage/>);
  fireEvent.click(await screen.findByRole('button', {name:'删除'}));
  pending('ancestor-original');
  act(() => window.dispatchEvent(new StorageEvent('storage', {key:operationLedgerKey('unknown-task-starts', context.session.userId!)})));
  const button = within(screen.getByRole('dialog', {name:'删除本机任务草稿？'})).getByRole('button', {name:'删除草稿'}) as HTMLButtonElement;
  expect(button.disabled).toBe(true);fireEvent.click(button);
  expect(JSON.parse(sessionStorage.getItem(dataKey('task-library'))!)).toHaveLength(1);
});
