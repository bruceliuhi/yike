// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { AppProvider } from "../../src/renderer/app/context";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { ConnectionsPage } from "../../src/renderer/pages/Connections";
import type { PlatformConnection } from "../../src/renderer/domain/models";
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
async function mount(
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
    // This fixture supplies its own OPEN/CHECK; do not inherit the real native flow observer.
    connectionLoginStatus: vi.fn().mockResolvedValue('WAITING_LOGIN'),
    ...overrides,
  };
  render(
    <AppProvider service={service}>
      <ConnectionsPage />
    </AppProvider>,
  );
  await act(async () => {});
  return service;
}

describe("平台连接", () => {
  it("连接服务失败不变成登录成功，检查按钮保持禁用", async () => {
    const service = await mount();
    expect(
      (
        screen.getByRole("button", {
          name: "我已完成登录，检查连接",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "打开登录窗口" }));
    await screen.findByText("平台登录服务尚未接通");
    expect(service.connect).toHaveBeenCalledWith("xhs", expect.any(AbortSignal));
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
    const service = await mount({
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
    await mount(
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

  it("打开窗口挂起会超时，可重试；晚到结果不能恢复等待状态", async () => {
    let finish!: () => void;
    const service = await mount({ connect: vi.fn()
      .mockImplementationOnce(() => new Promise<void>(resolve => { finish = resolve; }))
      .mockResolvedValue(undefined) });
    vi.useFakeTimers();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "打开登录窗口" })));
    expect(screen.getByText("正在打开登录窗口")).toBeTruthy();
    await act(async () => vi.advanceTimersByTimeAsync(30_000));
    expect(screen.getByText(/打开登录窗口超时/)).toBeTruthy();
    expect(screen.getByText("等待超时")).toBeTruthy();
    expect((screen.getByRole("button", { name: "打开登录窗口" }) as HTMLButtonElement).disabled).toBe(false);
    await act(async () => finish());
    expect(screen.queryByText("等待登录")).toBeNull();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "打开登录窗口" })));
    expect(screen.getByText("等待登录")).toBeTruthy();
    expect(service.connect).toHaveBeenCalledTimes(2);
  });

  it("连接检查挂起会超时，保留已打开状态供重试并忽略旧成功", async () => {
    let finish!: (value: PlatformConnection) => void;
    const connection: PlatformConnection = { platform: "xhs", status: "CONNECTED", accountId: "test-new", capabilities: ["search"] };
    const service = await mount({
      connect: vi.fn().mockResolvedValue(undefined),
      checkConnection: vi.fn().mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }))
        .mockResolvedValue(connection),
    });
    vi.useFakeTimers();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "打开登录窗口" })));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "我已完成登录，检查连接" })));
    await act(async () => vi.advanceTimersByTimeAsync(30_000));
    expect(screen.getByText(/检查连接超时/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "我已完成登录，检查连接" }) as HTMLButtonElement).disabled).toBe(false);
    await act(async () => finish({ ...connection, accountId: "test-stale" }));
    expect(screen.queryByText("账号已连接")).toBeNull();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "我已完成登录，检查连接" })));
    expect(screen.getByText("账号已连接")).toBeTruthy();
    expect(screen.queryByText("test-stale")).toBeNull();
    expect(service.checkConnection).toHaveBeenCalledTimes(2);
  });

  it("检查中取消返回原任务，晚到成功不会更新连接列表", async () => {
    let finish!: (value: PlatformConnection) => void;
    await mount({ connect: vi.fn().mockResolvedValue(undefined), checkConnection: vi.fn(() => new Promise<PlatformConnection>(resolve => { finish = resolve; })) },
      "/connections?connect=xhs&returnTo=" + encodeURIComponent("/tasks/new?step=connect"));
    fireEvent.click(screen.getByRole("button", { name: "打开登录窗口" }));
    await screen.findByText("等待登录");
    fireEvent.click(screen.getByRole("button", { name: "我已完成登录，检查连接" }));
    await screen.findByText("正在检查连接");
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    await waitFor(() => expect(window.location.hash).toBe("#/tasks/new?step=connect"));
    await act(async () => finish({ platform: "xhs", status: "CONNECTED", accountId: "late-account", capabilities: ["search"] }));
    expect(screen.queryByText("late-account")).toBeNull();
    expect(screen.queryByText("账号已连接")).toBeNull();
  });
});
