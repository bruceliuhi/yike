// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { parentRoute } from "../../src/renderer/app/App";
import { AppProvider, useApp } from "../../src/renderer/app/context";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import type { TaskRun } from "../../src/renderer/domain/models";
import { parseRoute, routeHref } from "../../src/renderer/domain/routes";
import { TasksPage } from "../../src/renderer/pages/Tasks";
import type { YikeService } from "../../src/renderer/services/contracts";

const run: TaskRun = {
  id: "TEST-return-monitor",
  name: "TEST平台上下文",
  mode: "monitor",
  status: "OFFLINE",
  platforms: ["web", "xhs"],
  platformStages: [
    { platform: "web", status: "NO_NEW" },
    { platform: "xhs", status: "OFFLINE" },
  ],
};
function RoutedTask() {
  const { sessionReady, route, navigate } = useApp();
  if (!sessionReady) return <p>TEST会话初始化</p>;
  return <>
    <output data-testid="route">{routeHref(route)}</output>
    {route.path.startsWith("/monitors/")
      ? <TasksPage />
      : <button onClick={() => navigate(parentRoute(route))}>TEST返回原任务</button>}
  </>;
}
function mount(task = run) {
  const service = {
    session: vi.fn().mockResolvedValue({ authenticated: true, userId: "TEST-return-" + crypto.randomUUID() }),
    tasks: vi.fn().mockResolvedValue([task]),
    profiles: vi.fn().mockResolvedValue([]),
    taskAction: vi.fn(),
    startTask: vi.fn(),
  } as unknown as YikeService;
  render(<AppProvider service={service}><RoutedTask /></AppProvider>);
  return service;
}
beforeEach(() => {
  clearLocalDrafts();
  sessionStorage.clear();
  localStorage.clear();
  history.replaceState(null, "", "#/monitors/TEST-return-monitor?filter=one&filter=two");
});
afterEach(() => { cleanup(); clearLocalDrafts(); });

it.each(["device", "connection"] as const)(
  "restores actual platform tab/non-first selection through asynchronous AppProvider %s return",
  async (inspection) => {
    const user = userEvent.setup();
    const service = mount({
      ...run,
      platformStages: [
        { platform: "web", status: "NO_NEW" },
        { platform: "xhs", status: inspection === "device" ? "OFFLINE" : "LOGIN_EXPIRED" },
      ],
    });
    await user.click(await screen.findByRole("tab", { name: "平台状态" }));
    await user.click(screen.getByRole("button", { name: "查看小红书状态" }));
    await user.click(screen.getByRole("button", { name: inspection === "device" ? "检查执行设备" : "重新连接" }));
    await screen.findByRole("button", { name: "TEST返回原任务" });
    const destination = parseRoute(window.location.hash);
    expect(destination.path).toBe(inspection === "device" ? "/settings" : "/connections");
    const back = parseRoute("#" + parentRoute(destination));
    expect(back.path).toBe("/monitors/TEST-return-monitor");
    expect(back.query.getAll("filter")).toEqual(["one", "two"]);
    // Real AppProvider hashchange unmounts TasksPage on departure and mounts
    // it again on return. A retained URI alone does not satisfy this contract.
    await user.click(screen.getByRole("button", { name: "TEST返回原任务" }));
    await waitFor(() => expect(screen.getByRole("tab", { name: "平台状态" }).getAttribute("aria-selected")).toBe("true"));
    expect(screen.getByRole("button", { name: "查看小红书状态" }).getAttribute("aria-pressed")).toBe("true");
    expect(service.taskAction).not.toHaveBeenCalled();
    expect(service.startTask).not.toHaveBeenCalled();
  },
);

it.each(["not-a-platform", "douyin"])(
  "does not restore unknown or unselected platform %s, or an unknown tab",
  async (platform) => {
    const user = userEvent.setup();
    history.replaceState(null, "", "#/monitors/TEST-return-monitor?tab=not-a-tab&platform=" + platform);
    mount();
    expect((await screen.findByRole("tab", { name: "搜索覆盖" })).getAttribute("aria-selected")).toBe("true");
    await user.click(screen.getByRole("tab", { name: "平台状态" }));
    expect(screen.getByRole("button", { name: "查看公开网站状态" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "查看小红书状态" }).getAttribute("aria-pressed")).toBe("false");
  },
);
