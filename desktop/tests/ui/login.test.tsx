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
import { AppProvider, useApp } from "../../src/renderer/app/context";
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
  vi.useRealTimers();
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

function LoginRouteProbe() {
  const { navigate } = useApp();
  return <button onClick={() => navigate("/login")}>打开登录</button>;
}

describe("登录", () => {
  it("从受保护页面打开登录时自动保留原工作位置", async () => {
    window.location.hash = "#/tasks/new?mode=monitor&step=connect";
    const service = {
      ...baseService,
      session: vi.fn().mockResolvedValue({ authenticated: false }),
    };
    render(
      <AppProvider service={service}>
        <LoginRouteProbe />
      </AppProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "打开登录" }));
    await waitFor(() =>
      expect(window.location.hash).toBe(
        "#/login?returnTo=%2Ftasks%2Fnew%3Fmode%3Dmonitor%26step%3Dconnect",
      ),
    );
  });

  it("登录成功后回到 returnTo 指定的工作位置", async () => {
    window.location.hash = "#/login?returnTo=%2Ftasks%2Fnew%3Fmode%3Dmonitor%26step%3Dconnect";
    cleanup();
    mount({
      session: vi.fn()
        .mockResolvedValueOnce({ authenticated: false })
        .mockResolvedValue({ authenticated: true, userId: "test-user" }),
      loginToken: vi.fn().mockResolvedValue({ authenticated: true, userId: "test-user" }),
    });
    fireEvent.click(screen.getByRole("button", { name: /使用已有访问凭证/ }));
    fireEvent.change(screen.getByLabelText("短期访问凭证"), { target: { value: "test-token" } });
    fireEvent.click(screen.getByRole("button", { name: "使用凭证登录" }));
    await waitFor(() => expect(window.location.hash).toBe("#/tasks/new?mode=monitor&step=connect"));
  });
  it("不展示绕过短信的临时访问码入口", async () => {
    mount();
    expect(screen.queryByRole('button',{name:'临时访问码登录'})).toBeNull();
    expect(screen.queryByLabelText('临时访问码')).toBeNull();
  });
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
  it("仅真实短信响应启动冷却，首次试用登录无需试用码", async () => {
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
    fireEvent.click(screen.getByRole("button", { name: "登录" }));
    await waitFor(()=>expect(service.login).toHaveBeenCalledWith("13800000000", "123456"));
    expect(screen.queryByLabelText("试用码")).toBeNull();
  });
  it("已激活客户也通过同一短信登录入口", async () => {
    const service = mount({
      requestCode: vi.fn().mockResolvedValue({ retryAfter: 60 }),
      login: vi.fn().mockResolvedValue({ authenticated: true, userId: "test-user" }),
      session: vi.fn()
        .mockResolvedValueOnce({ authenticated: false })
        .mockResolvedValue({ authenticated: true, userId: "test-user" }),
    });
    fireEvent.change(screen.getByLabelText("手机号码"), { target: { value: "13800000000" } });
    fireEvent.change(screen.getByLabelText("短信验证码"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));
    await waitFor(() => expect(service.login).toHaveBeenCalledWith("13800000000", "123456"));
  });
  it("短信供应商明确拒绝时不进入倒计时并提示稍后重试", async () => {
    const service = mount({
      requestCode: vi.fn().mockRejectedValue(new ServiceError("sms_delivery_rejected", "短信发送未确认，请稍后重试。", 502)),
    });
    fireEvent.change(screen.getByLabelText("手机号码"), {target: {value: "13800000000"}});
    fireEvent.click(screen.getByRole("button", {name: "获取验证码"}));
    await screen.findByText("短信发送未确认，请稍后重试。");
    expect(screen.queryByRole("button", {name: /秒后重试/})).toBeNull();
    expect((screen.getByRole("button", {name: "获取验证码"}) as HTMLButtonElement).disabled).toBe(false);
  });
  it("重新获取验证码会清除上一次登录错误", async () => {
    const service = mount({
      requestCode: vi.fn().mockResolvedValue({ retryAfter: 60 }),
      login: vi.fn().mockRejectedValue(new ServiceError("phone_auth_failed", "验证码无效或已过期，请重新核对或获取验证码。", 401)),
    });
    fireEvent.change(screen.getByLabelText("手机号码"), { target: { value: "13800000000" } });
    fireEvent.change(screen.getByLabelText("短信验证码"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));
    await screen.findByText("验证码无效或已过期，请重新核对或获取验证码。");
    fireEvent.click(screen.getByRole("button", { name: "获取验证码" }));
    await waitFor(() => expect(service.requestCode).toHaveBeenCalledOnce());
    expect(screen.queryByText("验证码无效或已过期，请重新核对或获取验证码。")).toBeNull();
  });
  it("已有凭证走真实登录方法，凭证不进入本机存储", async () => {
    const service = mount({
      session: vi.fn()
        .mockResolvedValueOnce({ authenticated: false })
        .mockResolvedValue({ authenticated: true, userId: "test-user" }),
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

  it.each([{ authenticated: false }, { authenticated: true }])("登录返回成功但刷新未建立有效身份时留在登录页：%j", async (identity) => {
    const service = mount({
      loginToken: vi.fn().mockResolvedValue({ authenticated: true, userId: "test-user" }),
      session: vi.fn().mockResolvedValueOnce({ authenticated: false }).mockResolvedValue(identity),
    });
    fireEvent.click(screen.getByRole("button", { name: /使用已有访问凭证/ }));
    fireEvent.change(screen.getByLabelText("短期访问凭证"), { target: { value: "test-only-token" } });
    fireEvent.click(screen.getByRole("button", { name: "使用凭证登录" }));
    await screen.findByText("登录会话尚未建立或已失效，请核对凭证后重试。");
    expect(service.session).toHaveBeenCalledTimes(2);
    expect(window.location.hash).not.toBe("#/workbench");
    expect((screen.getByLabelText("短期访问凭证") as HTMLInputElement).value).toBe("test-only-token");
  });

  it.each(["success", "failure"])("换手机号后忽略旧短信请求的晚到%s，可请求当前号码", async (outcome) => {
    let finish!: (value: {retryAfter: number}) => void;
    let fail!: (reason: Error) => void;
    const service = mount({ requestCode: vi.fn()
      .mockImplementationOnce(() => new Promise((resolve, reject) => { finish = resolve; fail = reject; }))
      .mockResolvedValue({ retryAfter: 60 }) });
    fireEvent.change(screen.getByLabelText("手机号码"), { target: { value: "13800000000" } });
    fireEvent.click(screen.getByRole("button", { name: "获取验证码" }));
    await waitFor(() => expect(service.requestCode).toHaveBeenCalledOnce());
    fireEvent.change(screen.getByLabelText("短信验证码"), { target: { value: "123456" } });
    fireEvent.change(screen.getByLabelText("手机号码"), { target: { value: "13900000000" } });
    await act(async () => outcome === "success" ? finish({ retryAfter: 120 }) : fail(new Error("旧号码错误")));
    expect(screen.queryByText("旧号码错误")).toBeNull();
    expect(screen.queryByRole("button", { name: "120 秒后重试" })).toBeNull();
    expect((screen.getByLabelText("短信验证码") as HTMLInputElement).value).toBe("");
    fireEvent.click(screen.getByRole("button", { name: "获取验证码" }));
    await screen.findByRole("button", { name: "60 秒后重试" });
    expect(service.requestCode).toHaveBeenLastCalledWith("13900000000");
  });

  it("登录时等待会话确认，未确认前不能重复提交", async () => {
    let finish!: (value: {authenticated: boolean; userId: string}) => void;
    const service = mount({
      login: vi.fn().mockResolvedValue({ authenticated: true, userId: "test-user" }),
      session: vi.fn().mockResolvedValueOnce({ authenticated: false }).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; })),
    });
    fireEvent.change(screen.getByLabelText("手机号码"), { target: { value: "13800000000" } });
    fireEvent.change(screen.getByLabelText("短信验证码"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));
    await waitFor(() => expect(service.session).toHaveBeenCalledTimes(2));
    expect(window.location.hash).not.toBe("#/workbench");
    expect((screen.getByRole("button", { name: "登录" }) as HTMLButtonElement).disabled).toBe(true);
    await act(async () => finish({ authenticated: true, userId: "test-user" }));
    await waitFor(() => expect(window.location.hash).toBe("#/workbench"));
    expect(service.login).toHaveBeenCalledOnce();
    expect(service.login).toHaveBeenCalledWith("13800000000", "123456");
  });

  it("短信请求挂起后超时，保留手机号并释放重试入口", async () => {
    const service = mount({ requestCode: vi.fn().mockImplementation(() => new Promise(() => {})) });
    await act(async () => {});
    vi.useFakeTimers();
    fireEvent.change(screen.getByLabelText("手机号码"), { target: { value: "13800000000" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "获取验证码" })));
    expect(service.requestCode).toHaveBeenCalledOnce();
    await act(async () => vi.advanceTimersByTimeAsync(30_000));
    expect(screen.getByText(/验证码请求超时，发送结果尚未确认/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "获取验证码" }) as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByLabelText("手机号码") as HTMLInputElement).value).toBe("13800000000");
    expect(window.location.hash).not.toBe("#/workbench");
  });

  it.each(["exchange", "session"])("登录%s挂起时超时释放表单，丢弃晚到成功后仍可重新登录", async (stage) => {
    let finish!: (value: {authenticated: boolean; userId: string}) => void;
    const pending = new Promise<{authenticated: boolean; userId: string}>(resolve => { finish = resolve; });
    const identity = { authenticated: true, userId: "test-current-user" };
    const service = mount({
      loginToken: stage === "exchange"
        ? vi.fn().mockReturnValueOnce(pending).mockResolvedValue(identity)
        : vi.fn().mockResolvedValue(identity),
      session: stage === "session"
        ? vi.fn().mockResolvedValueOnce({ authenticated: false }).mockReturnValueOnce(pending).mockResolvedValue(identity)
        : vi.fn().mockResolvedValueOnce({ authenticated: false }).mockResolvedValue(identity),
    });
    await act(async () => {});
    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: /使用已有访问凭证/ }));
    fireEvent.change(screen.getByLabelText("短期访问凭证"), { target: { value: "test-only-token" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "使用凭证登录" })));
    expect((screen.getByLabelText("短期访问凭证") as HTMLInputElement).disabled).toBe(true);
    await act(async () => vi.advanceTimersByTimeAsync(30_000));
    expect(screen.getByText(stage === "exchange"
      ? "登录请求超时，结果尚未确认。请稍后重试并重新确认会话。"
      : "会话确认超时，登录状态尚未核实。请稍后重试。")).toBeTruthy();
    expect((screen.getByLabelText("短期访问凭证") as HTMLInputElement).disabled).toBe(false);
    expect((screen.getByLabelText("短期访问凭证") as HTMLInputElement).value).toBe("test-only-token");
    await act(async () => finish({ authenticated: true, userId: "test-stale-user" }));
    expect(window.location.hash).not.toBe("#/workbench");
    expect(service.session).toHaveBeenCalledTimes(stage === "exchange" ? 1 : 2);
    fireEvent.change(screen.getByLabelText("短期访问凭证"), { target: { value: "test-current-token" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "使用凭证登录" })));
    expect(service.loginToken).toHaveBeenLastCalledWith("test-current-token");
    expect(window.location.hash).toBe("#/workbench");
  });
});
