// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { parentRoute } from "../../src/renderer/app/App";
import type { AppContextValue } from "../../src/renderer/app/context";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { newTaskDraft, type TaskRun } from "../../src/renderer/domain/models";
import { parseRoute } from "../../src/renderer/domain/routes";
import { ConnectionsPage } from "../../src/renderer/pages/Connections";
import { SettingsPage } from "../../src/renderer/pages/Settings";
import { TasksPage } from "../../src/renderer/pages/Tasks";
import { TaskWizardPage } from "../../src/renderer/pages/TaskWizard";
import type { YikeService } from "../../src/renderer/services/contracts";

let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
beforeEach(() => {
  clearLocalDrafts();
  localStorage.clear();
  sessionStorage.clear();
  context = {
    service: {
      profiles: vi.fn().mockResolvedValue([]),
      connections: vi.fn().mockResolvedValue([]),
      info: vi.fn().mockResolvedValue({
        version: "TEST",
        platform: "test",
        serviceConfigured: false,
      }),
      tasks: vi.fn().mockResolvedValue([]),
      taskAction: vi.fn(),
      startTask: vi.fn(),
      checkUpdate: vi.fn().mockRejectedValue(new Error("TEST未配置更新服务")),
    } as unknown as YikeService,
    session: {
      authenticated: true,
      userId: "TEST-task-navigation-" + crypto.randomUUID(),
    },
    sessionReady: true,
    route: parseRoute("#/collection"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
  };
});
afterEach(() => {
  cleanup();
  clearLocalDrafts();
});

it.each([
  ["web", "查看范围"],
  ["xhs", "连接账号"],
] as const)(
  "returns from %s inspection to the exact task connection step without replacing its draft",
  async (platform, label) => {
    const source =
      "/tasks/new?step=connect&mode=monitor&draft=TEST-original&filter=first&filter=second";
    context.route = parseRoute("#" + source);
    const draft = {
      ...newTaskDraft("monitor"),
      name: "TEST待配置监控",
      platforms: [platform],
    };
    sessionStorage.setItem(
      "yike.ui.draft.v1.task." + context.session.userId,
      JSON.stringify(draft),
    );
    const view = render(<TaskWizardPage />);
    fireEvent.click(await screen.findByRole("button", { name: label }));
    const destination = vi.mocked(context.navigate).mock.calls.at(-1)![0];
    expect(parseRoute("#" + destination).path).toBe("/connections");
    expect(parentRoute(parseRoute("#" + destination))).toBe(source);
    context.route = parseRoute("#" + destination);
    view.rerender(<ConnectionsPage />);
    if (platform === "xhs") {
      fireEvent.click(screen.getByRole("button", { name: "关闭连接小红书" }));
      expect(context.navigate).toHaveBeenLastCalledWith(source);
    }
    context.route = parseRoute("#" + source);
    view.rerender(<TaskWizardPage />);
    expect(screen.getByRole("button", { name: label })).toBeTruthy();
    const restored = JSON.parse(
      sessionStorage.getItem(
        "yike.ui.draft.v1.task." + context.session.userId,
      )!,
    );
    expect(restored).toMatchObject({
      id: draft.id,
      name: draft.name,
      mode: "monitor",
      platforms: [platform],
    });
    expect(context.service.startTask).not.toHaveBeenCalled();
  },
);

it("returns from device inspection to the same offline monitor", async () => {
  const run: TaskRun = {
    id: "TEST-offline:original.monitor",
    name: "TEST离线监控",
    mode: "monitor",
    status: "OFFLINE",
    platforms: ["web"],
    platformStages: [{ platform: "web", status: "OFFLINE" }],
  };
  const source =
    "/monitors/" +
    encodeURIComponent(run.id) +
    "?tab=platforms&filter=offline&platform=web";
  context.route = parseRoute("#" + source);
  vi.mocked(context.service.tasks).mockResolvedValue([run]);
  render(<TasksPage />);
  fireEvent.click(await screen.findByRole("tab", { name: "平台状态" }));
  fireEvent.click(screen.getByRole("button", { name: "检查执行设备" }));
  const destination = vi.mocked(context.navigate).mock.calls.at(-1)![0];
  expect(parseRoute("#" + destination).path).toBe("/settings");
  expect(parentRoute(parseRoute("#" + destination))).toBe(source);
  expect(context.service.taskAction).not.toHaveBeenCalled();
});

it("keeps the original task caller when switching between connections and device settings", async () => {
  const source = "/tasks/new?step=connect&mode=monitor&draft=TEST-original";
  const query = "?returnTo=" + encodeURIComponent(source);
  context.route = parseRoute("#/connections" + query);
  const view = render(<ConnectionsPage />);
  fireEvent.click(screen.getByRole("tab", { name: "设备与使用授权" }));
  expect(context.navigate).toHaveBeenLastCalledWith("/settings" + query);
  context.route = parseRoute("#/settings" + query);
  view.rerender(<SettingsPage />);
  await screen.findByText("TEST");
  expect(parentRoute(context.route)).toBe(source);
  fireEvent.click(screen.getByRole("tab", { name: "平台连接" }));
  expect(context.navigate).toHaveBeenLastCalledWith("/connections" + query);
  context.route = parseRoute("#/connections" + query);
  view.rerender(<ConnectionsPage />);
  expect(parentRoute(context.route)).toBe(source);
});

it.each([
  null,
  "https://outside.invalid/tasks/new",
  "//outside.invalid/tasks/new",
  "javascript:alert(1)",
  "/not-a-page?step=connect",
])(
  "keeps existing local fallbacks and drops an invalid caller (%s)",
  async (caller) => {
    const query =
      caller === null ? "" : "?returnTo=" + encodeURIComponent(caller);
    context.route = parseRoute("#/connections" + query);
    expect(parentRoute(context.route)).toBe("/workbench");
    expect(
      parentRoute(
        parseRoute(
          "#/connections?" +
            new URLSearchParams({
              connect: "xhs",
              ...(caller === null ? {} : { returnTo: caller }),
            }),
        ),
      ),
    ).toBe("/connections");
    const view = render(<ConnectionsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "设备与使用授权" }));
    expect(context.navigate).toHaveBeenLastCalledWith("/settings");
    context.route = parseRoute("#/settings" + query);
    view.rerender(<SettingsPage />);
    await screen.findByText("TEST");
    expect(parentRoute(context.route)).toBe("/connections");
    fireEvent.click(screen.getByRole("tab", { name: "平台连接" }));
    expect(context.navigate).toHaveBeenLastCalledWith("/connections");
  },
);
