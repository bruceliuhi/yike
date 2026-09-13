// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { AppProvider, useApp } from "../../src/renderer/app/context";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { SettingsPage } from "../../src/renderer/pages/Settings";
import { service as baseService } from "../../src/renderer/services/client";
import {
  ServiceError,
  type YikeService,
} from "../../src/renderer/services/contracts";

afterEach(() => {
  cleanup();
  clearLocalDrafts();
  window.history.replaceState(null, "", "/");
});
function mount(overrides: Partial<YikeService> = {}) {
  const service = {
    ...baseService,
    session: vi
      .fn()
      .mockResolvedValue({ authenticated: true, userId: "test-user" }),
    info: vi
      .fn()
      .mockResolvedValue({
        version: "0.2.0-test",
        platform: "darwin",
        serviceConfigured: false,
      }),
    activate: vi
      .fn()
      .mockRejectedValue(new ServiceError("UNAVAILABLE", "激活服务尚未接通")),
    logout: vi.fn().mockResolvedValue(undefined),
    copy: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  render(
    <AppProvider service={service}>
      <SettingsPage />
    </AppProvider>,
  );
  return service;
}

describe("设备与授权", () => {
  it('设置保留商业授权，自动连接准备不显示手动身份入口', async () => {
    const identity={getStatus:vi.fn(),prepare:vi.fn().mockResolvedValue({state:'READY',
      deviceId:'12345678-1234-1234-1234-123456789abc',credentialVersion:1})};
    mount({deviceIdentity:identity,management:undefined});
    await waitFor(()=>expect(identity.prepare).toHaveBeenCalledExactlyOnceWith({}));
    expect(screen.getByText('未取得商业设备绑定状态')).toBeTruthy();
    expect(screen.getByLabelText('授权码')).toBeTruthy();
    expect(screen.queryByRole('button',{name:/核验本机/})).toBeNull();
    expect(screen.queryByText('本机身份')).toBeNull();
    expect(screen.queryByRole('checkbox')).toBeNull();
    expect(document.body.textContent).not.toContain('12345678-1234-1234-1234-123456789abc');
    expect(identity.getStatus).not.toHaveBeenCalled();
  });
  it("会话变化立即卸载设置页时，退出仍会清草稿并导航", async () => {
    sessionStorage.setItem("yike.ui.draft.v1.test", "draft-only");
    const service = {
      ...baseService,
      session: vi
        .fn()
        .mockResolvedValueOnce({ authenticated: true, userId: "test-user" })
        .mockResolvedValue({ authenticated: false }),
      info: vi
        .fn()
        .mockResolvedValue({
          version: "test",
          platform: "darwin",
          serviceConfigured: false,
        }),
      logout: vi.fn().mockRejectedValue(new ServiceError("NETWORK", "离线")),
    };
    function SessionBoundPage() {
      const { session } = useApp();
      return session.authenticated ? (
        <SettingsPage key={session.userId} />
      ) : (
        <p>已离开设置页面</p>
      );
    }
    render(
      <AppProvider service={service}>
        <SessionBoundPage />
      </AppProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "退出登录" }));
    fireEvent.click(
      within(
        screen.getByRole("dialog", { name: "退出当前客户空间？" }),
      ).getByRole("button", { name: "退出登录" }),
    );
    await screen.findByText("已离开设置页面");
    await waitFor(() => expect(window.location.hash).toBe("#/login"));
    expect(sessionStorage.getItem("yike.ui.draft.v1.test")).toBeNull();
    expect(
      screen.getByText(
        "已离开客户空间并清除本机草稿，服务端注销结果尚未确认。",
      ),
    ).toBeTruthy();
  });
  it("离线退出后重查会话，清草稿并保留服务端结果未知提示", async () => {
    sessionStorage.setItem("yike.ui.draft.v1.test", "draft-only");
    const service = mount({
      logout: vi
        .fn()
        .mockRejectedValue(new ServiceError("NETWORK", "服务暂时无法连接")),
      session: vi
        .fn()
        .mockResolvedValueOnce({ authenticated: true, userId: "test-user" })
        .mockRejectedValue(new ServiceError("NETWORK", "会话无法读取")),
    });
    fireEvent.click(await screen.findByRole("button", { name: "退出登录" }));
    fireEvent.click(
      within(
        screen.getByRole("dialog", { name: "退出当前客户空间？" }),
      ).getByRole("button", { name: "退出登录" }),
    );
    await screen.findByText(
      "已离开客户空间并清除本机草稿，服务端注销结果尚未确认。",
    );
    expect(service.session).toHaveBeenCalledTimes(2);
    expect(sessionStorage.getItem("yike.ui.draft.v1.test")).toBeNull();
    await waitFor(() => expect(window.location.hash).toBe("#/login"));
    expect(screen.queryByText("退出成功")).toBeNull();
  });
  it("远端退出失败且会话仍有效时保留草稿与重试入口", async () => {
    sessionStorage.setItem("yike.ui.draft.v1.test", "draft-only");
    const service = mount({
      logout: vi
        .fn()
        .mockRejectedValue(new ServiceError("NETWORK", "服务暂时无法连接")),
    });
    fireEvent.click(await screen.findByRole("button", { name: "退出登录" }));
    fireEvent.click(
      within(
        screen.getByRole("dialog", { name: "退出当前客户空间？" }),
      ).getByRole("button", { name: "退出登录" }),
    );
    await screen.findByText("服务暂时无法连接");
    await waitFor(() => expect(service.session).toHaveBeenCalledTimes(2));
    expect(sessionStorage.getItem("yike.ui.draft.v1.test")).toBe("draft-only");
    expect(
      screen.getByRole("dialog", { name: "退出当前客户空间？" }),
    ).toBeTruthy();
    expect(window.location.hash).not.toBe("#/login");
  });
  it("使用实际运行信息并诚实报告激活失败", async () => {
    const service = mount();
    await screen.findByText("0.2.0-test");
    expect(screen.getByText("macOS")).toBeTruthy();
    expect(screen.queryByText(/配置服务地址|服务配置状态|支持与诊断/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "激活" }));
    expect(service.activate).not.toHaveBeenCalled();
    expect(screen.getByText("请输入授权码。")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("授权码"), {
      target: { value: "synthetic-activation-code" },
    });
    fireEvent.click(screen.getByRole("button", { name: "激活" }));
    await screen.findByText("激活服务尚未接通");
    expect(screen.queryByText("已激活")).toBeNull();
    expect((screen.getByLabelText("授权码") as HTMLInputElement).value).toBe(
      "synthetic-activation-code",
    );
  });
  it("联系支持可复制白名单诊断，但页面不展示技术内容", async () => {
    const service = mount();
    await screen.findByText("0.2.0-test");
    fireEvent.change(screen.getByLabelText("授权码"), {
      target: { value: "private-code" },
    });
    expect(screen.queryByRole("button", { name: "查看脱敏诊断" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "联系支持" }));
    expect(screen.queryByLabelText("脱敏诊断内容")).toBeNull();
    expect(screen.queryByText(/serviceConfigured|connectionPreparation/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "复制诊断信息" }));
    await waitFor(() => expect(service.copy).toHaveBeenCalledOnce());
    const content = vi.mocked(service.copy).mock.calls[0][0];
    expect(JSON.parse(content)).toEqual({
      product: "意客AI",
      version: "0.2.0-test",
      platform: "darwin",
      serviceConfigured: false,
    });
    expect(content).not.toContain("private-code");
    expect(content).not.toContain("test-user");
  });
  it("退出需确认，成功后清除本机草稿", async () => {
    sessionStorage.setItem("yike.ui.draft.v1.test", "draft-only");
    const service = mount({
      session: vi
        .fn()
        .mockResolvedValueOnce({ authenticated: true, userId: "test-user" })
        .mockResolvedValue({ authenticated: false }),
    });
    const button = await screen.findByRole("button", { name: "退出登录" });
    fireEvent.click(button);
    expect(service.logout).not.toHaveBeenCalled();
    const dialog = screen.getByRole("dialog", { name: "退出当前客户空间？" });
    fireEvent.click(within(dialog).getByRole("button", { name: "退出登录" }));
    await waitFor(() => expect(service.logout).toHaveBeenCalledOnce());
    await waitFor(() =>
      expect(sessionStorage.getItem("yike.ui.draft.v1.test")).toBeNull(),
    );
    expect(window.location.hash).toBe("#/login");
  });
  it("恢复服务未接通时不执行任何覆盖", async () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: "备份与恢复" }));
    expect(
      screen.getByText("客户数据恢复服务尚未接通，当前没有执行覆盖或恢复。"),
    ).toBeTruthy();
    expect(screen.queryByText("恢复成功")).toBeNull();
  });
});
