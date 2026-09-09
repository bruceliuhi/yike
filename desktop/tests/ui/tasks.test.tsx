// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { parseRoute } from "../../src/renderer/domain/routes";
import {
  newTaskDraft,
  type TaskDraft,
  type TaskRun,
} from "../../src/renderer/domain/models";
import {
  ServiceError,
  type YikeService,
} from "../../src/renderer/services/contracts";
import type { AppContextValue } from "../../src/renderer/app/context";
let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
const runs: TaskRun[] = [
  {
    id: "running-test",
    name: "测试运行任务",
    mode: "once",
    status: "RUNNING",
    platforms: ["xhs"],
  },
  {
    id: "failed-test",
    name: "测试失败任务",
    mode: "once",
    status: "FAILED",
    platforms: ["douyin"],
  },
  {
    id: "blocked-test",
    name: "测试待处理任务",
    mode: "once",
    status: "BLOCKED",
    platforms: ["zhihu"],
  },
  {
    id: "monitor-test",
    name: "测试监控任务",
    mode: "monitor",
    status: "PAUSED",
    platforms: ["web"],
  },
];
beforeEach(() => {
  clearLocalDrafts();
  sessionStorage.clear();
  localStorage.clear();
  context = {
    service: {
      tasks: vi.fn().mockResolvedValue(runs),
      taskAction: vi.fn().mockResolvedValue(undefined),
    } as unknown as YikeService,
    session: { authenticated: true, userId: crypto.randomUUID() },
    sessionReady: true,
    route: parseRoute("#/collection"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
  };
});
afterEach(cleanup);
function saveLibrary(): TaskDraft[] {
  const drafts = [
    {
      ...newTaskDraft(),
      id: "saved-once",
      name: "会话中的采集草稿",
      savedAt: "2026-09-09T01:00:00Z",
    },
    {
      ...newTaskDraft("monitor"),
      id: "saved-monitor",
      name: "会话中的监控草稿",
      savedAt: "2026-09-09T01:00:00Z",
    },
  ];
  sessionStorage.setItem(
    "yike.ui.draft.v1.task-library." + context.session.userId,
    JSON.stringify(drafts),
  );
  return drafts;
}
describe("task lists and local drafts", () => {
  it("filters local drafts by mode and search, then edits a real draft snapshot without starting it", async () => {
    const drafts = saveLibrary();
    render(<TasksPage />);
    await screen.findByText("测试运行任务");
    fireEvent.click(screen.getByRole("tab", { name: /本机草稿/ }));
    expect(screen.queryByText("测试运行任务")).toBeNull();
    expect(screen.queryByText("会话中的监控草稿")).toBeNull();
    fireEvent.change(screen.getByRole("textbox", { name: "搜索任务" }), {
      target: { value: "找不到的词" },
    });
    await screen.findByText("没有匹配任务");
    fireEvent.click(screen.getByRole("button", { name: "清除搜索" }));
    fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
    const restored = JSON.parse(
      sessionStorage.getItem(
        "yike.ui.draft.v1.task." + context.session.userId,
      )!,
    );
    expect(restored).toEqual(drafts[0]);
    expect(context.navigate).toHaveBeenCalledWith("/tasks/new");
    expect(context.service.taskAction).not.toHaveBeenCalled();
  });

  it("deletes only the chosen local draft after confirmation without calling the service", async () => {
    saveLibrary();
    render(<TasksPage />);
    fireEvent.click(screen.getByRole("tab", { name: /本机草稿/ }));
    fireEvent.click(screen.getByRole("button", { name: "删除" }));
    const dialog = screen.getByRole("dialog", { name: "删除本机任务草稿？" });
    expect(screen.getByText("会话中的采集草稿")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "删除草稿" }));
    await waitFor(() =>
      expect(screen.queryByText("会话中的采集草稿")).toBeNull(),
    );
    const remaining = JSON.parse(
      sessionStorage.getItem(
        "yike.ui.draft.v1.task-library." + context.session.userId,
      )!,
    );
    expect(remaining.map((draft: TaskDraft) => draft.id)).toEqual([
      "saved-monitor",
    ]);
    expect(context.service.taskAction).not.toHaveBeenCalled();
  });

  it("includes failed and blocked tasks in the needs-attention filter", async () => {
    render(<TasksPage />);
    await screen.findByText("测试待处理任务");
    fireEvent.click(screen.getByRole("tab", { name: "需要处理" }));
    expect(screen.getByText("测试失败任务")).toBeTruthy();
    expect(screen.getByText("测试待处理任务")).toBeTruthy();
    expect(screen.queryByText("测试运行任务")).toBeNull();
  });

  it("does not show a single collection run as a monitor detail through a changed URL", async () => {
    context.route = parseRoute("#/monitors/running-test");
    render(<TasksPage />);
    await screen.findByText("尚无可查看的监控详情");
    expect(screen.queryByText("测试运行任务")).toBeNull();
  });
});

function monitorRun(overrides: Partial<TaskRun> = {}): TaskRun {
  return {
    id: "monitor-test",
    name: "测试监控任务",
    mode: "monitor",
    status: "RUNNING",
    platforms: ["xhs", "douyin", "bilibili", "zhihu", "web"],
    ...overrides,
  };
}
function loadMonitor(run: TaskRun) {
  context.route = parseRoute("#/monitors/" + encodeURIComponent(run.id));
  context.service.tasks = vi.fn().mockResolvedValue([run]);
  const view = render(<TasksPage />);
  // R4 opens coverage by default. These R3 regressions explicitly inspect the retained platform tab.
  void screen
    .findByRole("tab", { name: "平台状态" })
    .then((tab) => fireEvent.click(tab));
  return view;
}
describe("monitor detail from execution service data", () => {
  it("distinguishes actual platform states and returns to the same monitor after reconnecting", async () => {
    const run = monitorRun({
      platformStages: [
        {
          platform: "xhs",
          status: "LOGIN_EXPIRED",
          reason: "测试登录失效原因",
          accountName: "测试账号",
        },
        {
          platform: "douyin",
          status: "RATE_LIMITED",
          nextRetryAt: "2026-09-09T06:00:00Z",
          reason: "测试限频原因",
        },
        {
          platform: "bilibili",
          status: "RUNNING",
          phase: "读取公开内容",
          newCount: 3,
        },
        { platform: "zhihu", status: "NO_NEW", newCount: 0 },
        { platform: "web", status: "OFFLINE" },
      ],
      statistics: { today: 3, week: 8 },
    });
    loadMonitor(run);
    await screen.findByRole("heading", { name: "测试监控任务", level: 1 });
    const table = within(screen.getByRole("region", { name: "平台运行状态" }));
    const aside = within(
      screen.getByRole("complementary", { name: "平台状态详情" }),
    );
    expect(table.getByText("登录失效")).toBeTruthy();
    expect(table.getByText("暂时受限")).toBeTruthy();
    expect(table.getByText("运行中")).toBeTruthy();
    expect(table.getByText("暂无新增")).toBeTruthy();
    expect(aside.getByText("测试登录失效原因")).toBeTruthy();
    fireEvent.click(aside.getByRole("button", { name: "重新连接" }));
    const destination = vi.mocked(context.navigate).mock.calls.at(-1)![0];
    const url = new URL(destination, "https://test.invalid");
    expect(url.pathname).toBe("/connections");
    expect(url.searchParams.get("connect")).toBe("xhs");
    expect(url.searchParams.get("returnTo")).toBe("/monitors/monitor-test");
    fireEvent.click(table.getByRole("button", { name: "查看抖音状态" }));
    expect(aside.getByText("测试限频原因")).toBeTruthy();
    expect(aside.getByText("最早重试时间")).toBeTruthy();
    expect(aside.queryByRole("button", { name: "重试任务" })).toBeNull();
    fireEvent.click(table.getByRole("button", { name: "查看B站状态" }));
    expect(aside.getByText("读取公开内容")).toBeTruthy();
    fireEvent.click(table.getByRole("button", { name: "查看知乎状态" }));
    expect(aside.getByText("本次执行未发现新增线索。")).toBeTruthy();
    fireEvent.click(table.getByRole("button", { name: "查看公开网站状态" }));
    fireEvent.click(aside.getByRole("button", { name: "检查执行设备" }));
    expect(context.navigate).toHaveBeenLastCalledWith("/settings");
    const statistics = within(screen.getByRole("region", { name: "执行统计" }));
    expect(statistics.getByText("3")).toBeTruthy();
    expect(statistics.getAllByText("—")).toHaveLength(2);
    expect(context.service.taskAction).not.toHaveBeenCalled();
  });
  it("does not turn absent execution data into waiting states, zero counts, or example events", async () => {
    loadMonitor(monitorRun({ platforms: ["web"], status: "PAUSED" }));
    await screen.findByRole("heading", { name: "测试监控任务", level: 1 });
    const table = within(screen.getByRole("region", { name: "平台运行状态" }));
    expect(table.getByText("待读取")).toBeTruthy();
    expect(table.queryByText("等待执行")).toBeNull();
    const statistics = within(screen.getByRole("region", { name: "执行统计" }));
    expect(statistics.getAllByText("—")).toHaveLength(4);
    expect(statistics.queryByText("0")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "执行记录" }));
    expect(screen.getByText("暂无运行记录")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "任务配置" }));
    expect(screen.getAllByText("待读取").length).toBeGreaterThan(4);
    expect(screen.queryByText(/每日/)).toBeNull();
  });
  it("renders the service profile version, schedule, events, and failure reason without deriving a next run", async () => {
    loadMonitor(
      monitorRun({
        status: "PARTIAL",
        profileId: "profile-test",
        profileName: "测试展台服务画像",
        profileVersion: 7,
        keywords: ["测试词一", "测试词二"],
        regions: "测试区域",
        lastRunAt: "2026-09-09T02:00:00Z",
        failureReason: "测试部分平台失败",
        schedule: {
          kind: "interval",
          times: [],
          interval: 3,
          start: "09:00",
          end: "18:00",
          timezone: "Asia/Shanghai",
        },
        events: [
          {
            id: "event-test",
            occurredAt: "2026-09-09T02:01:00Z",
            platform: "xhs",
            message: "测试平台会话失效",
            level: "warning",
          },
        ],
      }),
    );
    await screen.findByText("测试部分平台失败");
    fireEvent.click(screen.getByRole("tab", { name: "执行记录" }));
    expect(screen.getByText("测试平台会话失效")).toBeTruthy();
    expect(screen.getByText("提醒")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "任务配置" }));
    expect(screen.getByText("测试展台服务画像")).toBeTruthy();
    expect(screen.getByText("v7")).toBeTruthy();
    expect(screen.getByText("每 3 小时")).toBeTruthy();
    expect(screen.getByText("09:00–18:00")).toBeTruthy();
    expect(screen.getByText("下次计划").nextElementSibling?.textContent).toBe(
      "—",
    );
    expect(context.service.taskAction).not.toHaveBeenCalled();
  });
  it("shows an unavailable detail as a service error without inventing a monitor", async () => {
    context.route = parseRoute("#/monitors/unavailable");
    context.service.tasks = vi
      .fn()
      .mockRejectedValue(
        new ServiceError("CAPABILITY_UNAVAILABLE", "监控执行服务尚未接通", 501),
      );
    render(<TasksPage />);
    await screen.findByText("监控执行服务尚未接通");
    expect(screen.queryByRole("region", { name: "平台运行状态" })).toBeNull();
    expect(screen.queryByRole("button", { name: "暂停任务" })).toBeNull();
  });
  it("keeps a malformed detail URL in the missing-task state instead of crashing", async () => {
    context.route = parseRoute("#/monitors/%E0%A4%A");
    render(<TasksPage />);
    await screen.findByText("尚无可查看的监控详情");
    expect(context.service.taskAction).not.toHaveBeenCalled();
  });
});

describe("actual task list pagination and filters", () => {
  it("paginates returned rows, resets on platform/date filters and never invents missing update dates", async () => {
    context.service.tasks = vi.fn().mockResolvedValue(
      Array.from({ length: 23 }, (_, i) => ({
        ...runs[0],
        id: `task-${i}`,
        name: `分页任务 ${i}`,
        platforms: [i % 2 ? "xhs" : "web"],
        updatedAt:
          i === 22
            ? undefined
            : i < 12
              ? "2026-09-08T00:00:00Z"
              : "2026-09-10T00:00:00Z",
      })),
    );
    render(<TasksPage />);
    await screen.findByText("分页任务 0");
    expect(screen.queryByText("分页任务 10")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    expect(screen.getByText("分页任务 10")).toBeTruthy();
    fireEvent.change(screen.getByRole("combobox", { name: "筛选任务平台" }), {
      target: { value: "web" },
    });
    await screen.findByText("分页任务 0");
    expect(screen.queryByText("分页任务 1")).toBeNull();
    fireEvent.change(screen.getByLabelText("任务更新开始日期"), {
      target: { value: "2026-09-09" },
    });
    expect(screen.getByText("分页任务 12")).toBeTruthy();
    expect(screen.queryByText("分页任务 0")).toBeNull();
    expect(screen.queryByText("分页任务 22")).toBeNull();
    fireEvent.change(screen.getByLabelText("任务更新结束日期"), {
      target: { value: "2026-09-08" },
    });
    expect(screen.getByText("开始日期不能晚于结束日期。")).toBeTruthy();
    expect(screen.queryByText("分页任务 12")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "清除筛选" }));
    expect(screen.getByText("分页任务 0")).toBeTruthy();
  });
  it("prevents deleting a draft whose original startup has not been reconciled", async () => {
    saveLibrary();
    localStorage.setItem(
      "yike.ui.operation.v1.unknown-task-starts." + context.session.userId,
      JSON.stringify({ "saved-once": "task:saved-once:1" }),
    );
    render(<TasksPage />);
    fireEvent.click(screen.getByRole("tab", { name: /本机草稿/ }));
    expect(
      (screen.getByRole("button", { name: "删除" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "删除" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByText("本机草稿 · 未启动")).toBeNull();
    expect(screen.getAllByText("启动结果待确认")).toHaveLength(2);
  });
});
it("paginates and filters actual execution events without fabricating a timestamp", async () => {
  loadMonitor(
    monitorRun({
      events: Array.from({ length: 13 }, (_, i) => ({
        id: `event-${i}`,
        message: `实际测试记录 ${i}`,
        platform: i % 2 ? "xhs" : "web",
        occurredAt:
          i === 12
            ? undefined
            : i < 6
              ? "2026-09-08T00:00:00Z"
              : "2026-09-10T00:00:00Z",
      })),
    }),
  );
  await screen.findByRole("heading", { name: "测试监控任务", level: 1 });
  fireEvent.click(screen.getByRole("tab", { name: "执行记录" }));
  expect(screen.queryByText("实际测试记录 10")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  expect(screen.getByText("实际测试记录 12")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("记录开始日期"), {
    target: { value: "2026-09-09" },
  });
  expect(screen.queryByText("实际测试记录 12")).toBeNull();
  expect(screen.getByText("实际测试记录 6")).toBeTruthy();
  fireEvent.change(screen.getByRole("combobox", { name: "筛选执行记录平台" }), {
    target: { value: "xhs" },
  });
  expect(screen.queryByText("实际测试记录 6")).toBeNull();
  expect(screen.getByText("实际测试记录 7")).toBeTruthy();
});
