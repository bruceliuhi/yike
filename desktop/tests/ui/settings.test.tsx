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
  it.each(['READY', 'NOT_PREPARED'] as const)('直接显示只读本机状态 %s 且不误当商业绑定', async state => {
    const identity={getStatus:vi.fn().mockResolvedValue(state==='READY'?
      {state,deviceId:'12345678-1234-1234-1234-123456789abc',credentialVersion:1}:{state}),prepare:vi.fn()};
    mount({deviceIdentity:identity,management:undefined});
    await screen.findByText(state==='READY'?'上次身份核验通过':'尚未核验本机身份');
    expect(screen.getByText('未取得商业设备绑定状态')).toBeTruthy();
    expect(screen.queryByText('尚未完成绑定核验')).toBeNull();
    expect(screen.getByText(/本机身份核验无需输入授权码/)).toBeTruthy();
    expect(identity.prepare).not.toHaveBeenCalled();
  });
  it('坏身份DTO不显示成功或秘密，也不自动核验', async () => {
    const identity={getStatus:vi.fn().mockResolvedValue({state:'READY',deviceId:'secret',privateKey:'private-key'}),prepare:vi.fn()};
    mount({deviceIdentity:identity});
    await screen.findByText('本机身份状态读取失败，请打开核验入口重查。');
    expect(screen.queryByText('上次身份核验通过')).toBeNull();
    expect(document.body.textContent).not.toContain('private-key');
    expect(identity.prepare).not.toHaveBeenCalled();
  });
  it('关闭身份弹窗后刷新外层只读状态', async () => {
    const identity={getStatus:vi.fn().mockResolvedValue({state:'NOT_PREPARED'}),prepare:vi.fn()};
    mount({deviceIdentity:identity});
    await screen.findByText('尚未核验本机身份');
    fireEvent.click(screen.getByRole('button',{name:'核验本机身份'}));
    const modal=screen.getByRole('dialog',{name:'核验本机设备身份'});
    await within(modal).findByText('尚未核验本机身份');
    identity.getStatus.mockResolvedValue({state:'READY',deviceId:'12345678-1234-1234-1234-123456789abc',credentialVersion:1});
    fireEvent.click(within(modal).getByRole('button',{name:'关闭核验本机设备身份'}));
    await screen.findByText('上次身份核验通过');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(identity.prepare).not.toHaveBeenCalled();
  });
  it('切换账号时不接受上一账号迟到的READY', async () => {
    let resolveOld!: (value:unknown)=>void;
    const identity={getStatus:vi.fn().mockImplementationOnce(()=>new Promise(r=>{resolveOld=r;}))
      .mockResolvedValue({state:'NOT_PREPARED'}),prepare:vi.fn()};
    const service={...baseService,deviceIdentity:identity,
      info:vi.fn().mockResolvedValue({version:'test',platform:'win32',serviceConfigured:true}),
      session:vi.fn().mockResolvedValueOnce({authenticated:true,userId:'a'})
        .mockResolvedValue({authenticated:true,userId:'b'})};
    function Harness(){const {refreshSession}=useApp();return <>
      <button onClick={()=>void refreshSession()}>切换测试账号</button><SettingsPage/></>;}
    render(<AppProvider service={service}><Harness/></AppProvider>);
    await waitFor(()=>expect(identity.getStatus).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole('button',{name:'切换测试账号'}));
    await screen.findByText('尚未核验本机身份');
    await act(async()=>resolveOld({state:'READY',deviceId:'12345678-1234-1234-1234-123456789abc',credentialVersion:1}));
    expect(screen.queryByText('上次身份核验通过')).toBeNull();
    expect(identity.prepare).not.toHaveBeenCalled();
  });
  it.each([{id:'space-b',version:1},{id:'space-a',version:2}])('同账号切换空间作用域 %j 不接受旧READY', async accountScope => {
    let resolveOld!: (value:unknown)=>void;
    const identity={getStatus:vi.fn().mockImplementationOnce(()=>new Promise(r=>{resolveOld=r;}))
      .mockResolvedValue({state:'NOT_PREPARED'}),prepare:vi.fn()};
    const service={...baseService,deviceIdentity:identity,
      info:vi.fn().mockResolvedValue({version:'test',platform:'win32',serviceConfigured:true}),
      session:vi.fn().mockResolvedValueOnce({authenticated:true,userId:'a',accountScope:{id:'space-a',version:1}})
        .mockResolvedValue({authenticated:true,userId:'a',accountScope})};
    function Harness(){const {refreshSession}=useApp();return <>
      <button onClick={()=>void refreshSession()}>切换测试空间</button><SettingsPage/></>;}
    render(<AppProvider service={service}><Harness/></AppProvider>);
    await waitFor(()=>expect(identity.getStatus).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole('button',{name:'切换测试空间'}));
    await screen.findByText('尚未核验本机身份');
    await act(async()=>resolveOld({state:'READY',deviceId:'12345678-1234-1234-1234-123456789abc',credentialVersion:1}));
    expect(screen.queryByText('上次身份核验通过')).toBeNull();
    expect(identity.prepare).not.toHaveBeenCalled();
  });
  it('复用身份桥切换服务不接受旧READY', async () => {
    let resolveOld!: (value:unknown)=>void;
    const identity={getStatus:vi.fn().mockImplementationOnce(()=>new Promise(r=>{resolveOld=r;}))
      .mockResolvedValue({state:'NOT_PREPARED'}),prepare:vi.fn()};
    const service={...baseService,deviceIdentity:identity,
      info:vi.fn().mockResolvedValue({version:'test',platform:'win32',serviceConfigured:true}),
      session:vi.fn().mockResolvedValue({authenticated:true,userId:'a',accountScope:{id:'space-a',version:1}})};
    const view=render(<AppProvider service={service}><SettingsPage/></AppProvider>);
    await waitFor(()=>expect(identity.getStatus).toHaveBeenCalledOnce());
    view.rerender(<AppProvider service={{...service}}><SettingsPage/></AppProvider>);
    await screen.findByText('尚未核验本机身份');
    await act(async()=>resolveOld({state:'READY',deviceId:'12345678-1234-1234-1234-123456789abc',credentialVersion:1}));
    expect(screen.queryByText('上次身份核验通过')).toBeNull();
    expect(identity.prepare).not.toHaveBeenCalled();
  });
  it('未登录不读取或核验本机身份', async () => {
    const identity={getStatus:vi.fn(),prepare:vi.fn()};
    mount({deviceIdentity:identity,session:vi.fn().mockResolvedValue({authenticated:false})});
    await screen.findByText('0.2.0-test');
    expect(screen.queryByRole('button',{name:'核验本机身份'})).toBeNull();
    expect(identity.getStatus).not.toHaveBeenCalled();
    expect(identity.prepare).not.toHaveBeenCalled();
  });
  it("正常本机身份入口使用专用核验，不借管理接口绑定或冒称平台连接", async () => {
    const identity={getStatus:vi.fn().mockResolvedValue({state:'NOT_PREPARED'}),prepare:vi.fn().mockResolvedValue({state:'READY',deviceId:'12345678-1234-1234-1234-123456789abc',credentialVersion:1})};
    mount({deviceIdentity:identity});
    const button=await screen.findByRole('button',{name:'核验本机身份'});
    fireEvent.click(button);
    const modal=screen.getByRole('dialog',{name:'核验本机设备身份'});
    const checkbox=within(modal).getByRole('checkbox',{name:'确认在当前账号下核验本机设备'});
    await waitFor(()=>expect((checkbox as HTMLInputElement).disabled).toBe(false));
    fireEvent.click(checkbox);
    fireEvent.click(within(modal).getByRole('button',{name:'核验本机设备'}));
    await within(modal).findByText('上次身份核验通过');
    expect(identity.prepare).toHaveBeenCalledExactlyOnceWith({});
    expect(within(modal).getByText(/不代表平台已连接或使用授权已激活/)).toBeTruthy();
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
    expect(screen.getByText("尚未配置服务地址")).toBeTruthy();
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
  it("诊断仅含实际运行信息，不包含凭证或业务记录", async () => {
    const service = mount();
    await screen.findByText("0.2.0-test");
    fireEvent.change(screen.getByLabelText("授权码"), {
      target: { value: "private-code" },
    });
    fireEvent.click(screen.getByRole("button", { name: "查看脱敏诊断" }));
    const content = (
      screen.getByLabelText("脱敏诊断内容") as HTMLTextAreaElement
    ).value;
    expect(JSON.parse(content)).toEqual({
      product: "意客AI",
      version: "0.2.0-test",
      platform: "darwin",
      serviceConfigured: false,
    });
    expect(content).not.toContain("private-code");
    expect(content).not.toContain("test-user");
    fireEvent.click(screen.getByRole("button", { name: "复制脱敏诊断" }));
    await waitFor(() => expect(service.copy).toHaveBeenCalledWith(content));
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
