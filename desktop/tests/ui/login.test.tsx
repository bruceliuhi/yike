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
import { LoginPage } from "../../src/renderer/pages/Login";
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
    session: vi.fn().mockResolvedValue({ authenticated: false }),
    requestCode: vi
      .fn()
      .mockRejectedValue(new ServiceError("UNAVAILABLE", "短信服务尚未接通")),
    login: vi.fn(),
    loginToken: vi.fn(),
    ...overrides,
  };
  render(
    <AppProvider service={service}>
      <LoginPage />
    </AppProvider>,
  );
  return service;
}

describe("登录", () => {
  it("验证手机号并保留失败输入，短信服务失败不会进入倒计时", async () => {
    const service = mount();
    fireEvent.click(screen.getByRole("button", { name: "获取验证码" }));
    expect(service.requestCode).not.toHaveBeenCalled();
    expect(screen.getByText("请输入 11 位手机号码。")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("手机号码"), {
      target: { value: "13800000000" },
    });
    fireEvent.click(screen.getByRole("button", { name: "获取验证码" }));
    await screen.findByText("短信服务尚未接通");
    expect((screen.getByLabelText("手机号码") as HTMLInputElement).value).toBe(
      "13800000000",
    );
    expect(screen.getByRole("button", { name: "获取验证码" })).toBeTruthy();
    expect(service.login).not.toHaveBeenCalled();
  });
  it("仅真实短信响应启动冷却，并校验验证码与试用码", async () => {
    const service = mount({
      requestCode: vi.fn().mockResolvedValue({ retryAfter: 60 }),
    });
    fireEvent.change(screen.getByLabelText("手机号码"), {
      target: { value: "13800000000" },
    });
    fireEvent.click(screen.getByRole("button", { name: "获取验证码" }));
    const cooldown = await screen.findByRole("button", { name: "60 秒后重试" });
    expect((cooldown as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "登录" }));
    expect(service.login).not.toHaveBeenCalled();
    expect(screen.getByText("请输入 6 位短信验证码。")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("短信验证码"), {
      target: { value: "123456" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "首次使用，输入试用码开通" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "登录" }));
    expect(screen.getByText("请输入试用码，或收起试用开通。")).toBeTruthy();
  });
  it("已有凭证走真实登录方法，凭证不进入本机存储", async () => {
    const service = mount({
      loginToken: vi
        .fn()
        .mockResolvedValue({ authenticated: true, userId: "test-user" }),
    });
    fireEvent.click(screen.getByRole("button", { name: /使用已有访问凭证/ }));
    fireEvent.change(screen.getByLabelText("短期访问凭证"), {
      target: { value: "synthetic-test-token" },
    });
    fireEvent.click(screen.getByRole("button", { name: "使用凭证登录" }));
    await waitFor(() =>
      expect(service.loginToken).toHaveBeenCalledWith("synthetic-test-token"),
    );
    await waitFor(() => expect(window.location.hash).toBe("#/workbench"));
    expect(
      JSON.stringify({ ...sessionStorage, ...localStorage }),
    ).not.toContain("synthetic-test-token");
    expect(
      (screen.getByLabelText("短期访问凭证") as HTMLInputElement).value,
    ).toBe("");
  });
});
