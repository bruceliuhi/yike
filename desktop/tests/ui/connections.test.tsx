// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { AppProvider } from "../../src/renderer/app/context";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { ConnectionsPage } from "../../src/renderer/pages/Connections";
import { service as baseService } from "../../src/renderer/services/client";
import {
  ServiceError,
  type YikeService,
} from "../../src/renderer/services/contracts";

afterEach(() => {
  cleanup();
  clearLocalDrafts();
  window.history.replaceState(null, "", "/");
  vi.useRealTimers();
});
function mount(
  overrides: Partial<YikeService> = {},
  path = "/connections?connect=xhs",
) {
  window.history.replaceState(null, "", "#" + path);
  const service = {
    ...baseService,
    session: vi
      .fn()
      .mockResolvedValue({ authenticated: true, userId: "test-user" }),
    connections: vi.fn().mockResolvedValue([]),
    connect: vi
      .fn()
      .mockRejectedValue(
        new ServiceError("UNAVAILABLE", "平台登录服务尚未接通"),
      ),
    checkConnection: vi.fn(),
    ...overrides,
  };
  render(
    <AppProvider service={service}>
      <ConnectionsPage />
    </AppProvider>,
  );
  return service;
}

describe("平台连接", () => {
  it("连接服务失败不变成登录成功，检查按钮保持禁用", async () => {
    const service = mount();
    expect(
      (
        screen.getByRole("button", {
          name: "我已完成登录，检查连接",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "打开登录窗口" }));
    await screen.findByText("平台登录服务尚未接通");
    expect(service.connect).toHaveBeenCalledWith("xhs");
    expect(service.checkConnection).not.toHaveBeenCalled();
    expect(screen.queryByText("账号已连接")).toBeNull();
    expect(
      (
        screen.getByRole("button", {
          name: "我已完成登录，检查连接",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });
  it("原生窗口已打开后才检查；能力不足不会当作全部通过", async () => {
    const service = mount({
      connect: vi.fn().mockResolvedValue(undefined),
      checkConnection: vi
        .fn()
        .mockResolvedValue({
          platform: "xhs",
          status: "CONNECTED",
          accountId: "fixture-account",
          capabilities: [],
        }),
    });
    fireEvent.click(screen.getByRole("button", { name: "打开登录窗口" }));
    await screen.findByText("等待登录");
    fireEvent.click(
      screen.getByRole("button", { name: "我已完成登录，检查连接" }),
    );
    await screen.findByText("账号已连接");
    expect(service.checkConnection).toHaveBeenCalledWith("xhs");
    expect(
      screen.getByText(
        "账号连接成功，但尚无已验证的采集或触达能力；任务启动条件仍需检查。",
      ),
    ).toBeTruthy();
  });
  it("取消返回原任务并忽略过期的打开窗口响应", async () => {
    let finish: () => void = () => {};
    const promise = new Promise<void>((resolve) => {
      finish = resolve;
    });
    mount(
      { connect: vi.fn().mockReturnValue(promise) },
      "/connections?connect=xhs&returnTo=" +
        encodeURIComponent("/tasks/new?step=platforms"),
    );
    fireEvent.click(screen.getByRole("button", { name: "打开登录窗口" }));
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    await waitFor(() =>
      expect(window.location.hash).toBe("#/tasks/new?step=platforms"),
    );
    finish();
    await waitFor(() => expect(screen.queryByText("等待登录")).toBeNull());
  });
});
