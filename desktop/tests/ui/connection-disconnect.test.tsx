// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { AppContextValue } from "../../src/renderer/app/context";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { operationLedgerKey } from "../../src/renderer/app/operationLedger";
import { parseRoute } from "../../src/renderer/domain/routes";
import type { PlatformConnection } from "../../src/renderer/domain/models";
import { ConnectionsPage } from "../../src/renderer/pages/Connections";
import { service as baseService } from "../../src/renderer/services/client";

let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
const account: PlatformConnection = {
  platform: "xhs",
  status: "CONNECTED",
  accountId: "TEST-account-a",
  accountName: "TEST 账号 A",
  capabilities: ["search"],
};
const disconnected: PlatformConnection = {
  ...account,
  status: "DISCONNECTED",
  capabilities: [],
};
const ledgerKey = (user = "TEST-disconnect") =>
  operationLedgerKey("connection-disconnects", user);
const ledger = (user?: string): Record<string, string> =>
  JSON.parse(localStorage.getItem(ledgerKey(user)) || "{}");
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
beforeEach(() => {
  localStorage.clear();
  context = {
    session: { authenticated: true, userId: "TEST-disconnect" },
    route: parseRoute("#/connections"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
    service: {
      ...baseService,
      session: vi.fn(async () => context.session),
      connections: vi.fn().mockResolvedValue([account]),
      checkConnection: vi.fn().mockResolvedValue(account),
      disconnect: vi.fn().mockResolvedValue(undefined),
    },
  };
});
afterEach(() => {
  cleanup();
  clearLocalDrafts();
  localStorage.clear();
  vi.useRealTimers();
  vi.restoreAllMocks();
});
async function mount() {
  const view = render(<ConnectionsPage />);
  await screen.findByText("TEST 账号 A");
  return view;
}
async function start() {
  fireEvent.click(screen.getByRole("button", { name: "断开" }));
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: "断开连接" })),
  );
}
describe("P16 断开连接的有界等待与原账号核对", () => {
  it("预检中取消后，晚到的相同账号也不触发断开", async () => {
    const check = deferred<PlatformConnection>();
    vi.mocked(context.service.checkConnection).mockReturnValue(check.promise);
    await mount();
    await start();
    fireEvent.click(screen.getByRole("button", { name: "取消等待并关闭" }));
    await act(async () => check.resolve(account));
    expect(context.service.disconnect).not.toHaveBeenCalled();
    expect(ledger()).toEqual({});
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("预检期间出现同平台未决记录，派发前重新读锁并拒绝重复", async () => {
    const check = deferred<PlatformConnection>();
    vi.mocked(context.service.checkConnection).mockReturnValue(check.promise);
    await mount();
    await start();
    const original = JSON.stringify([
      "xhs",
      "TEST-account-a",
      "TEST-concurrent-request",
    ]);
    localStorage.setItem(
      ledgerKey(),
      JSON.stringify({ [original]: "PENDING" }),
    );
    await act(async () => check.resolve(account));
    expect(context.service.disconnect).not.toHaveBeenCalled();
    expect(ledger()).toEqual({ [original]: "PENDING" });
    expect(screen.getByText(/该平台已有断开请求待核对/)).toBeTruthy();
  });

  it("原生登录入口也读取未决锁，损坏存储不能绕过保护", async () => {
    context.route = parseRoute("#/connections?connect=xhs");
    context.service.connect = vi.fn().mockResolvedValue(undefined);
    await mount();
    localStorage.setItem(ledgerKey(), "not-json");
    fireEvent.click(screen.getByRole("button", { name: "打开登录窗口" }));
    expect(context.service.connect).not.toHaveBeenCalled();
    expect(screen.getByText(/操作确认记录暂时无法可靠保存/)).toBeTruthy();
  });

  it("收到原回执并读到原账号断开后才清锁，不用void响应直接报成功", async () => {
    vi.mocked(context.service.checkConnection)
      .mockResolvedValueOnce(account)
      .mockResolvedValue(disconnected);
    await mount();
    await start();
    await waitFor(() =>
      expect(context.notify).toHaveBeenCalledWith(
        "原账号已断开，并已核对当前连接状态。",
        "success",
      ),
    );
    expect(context.service.disconnect).toHaveBeenCalledExactlyOnceWith("xhs");
    expect(context.service.checkConnection).toHaveBeenCalledTimes(2);
    expect(ledger()).toEqual({});
  });

  it("挂起30秒释放等待；晚到ACK仅更新原记录，核对前不能再次断开或重新连接", async () => {
    const pending = deferred<void>();
    vi.mocked(context.service.disconnect).mockReturnValue(pending.promise);
    await mount();
    vi.useFakeTimers();
    await start();
    expect(Object.values(ledger())).toEqual(["PENDING"]);
    await act(async () => vi.advanceTimersByTimeAsync(30_000));
    expect(screen.getByText(/断开请求等待超时/)).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "关闭" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false);
    const before = Object.keys(ledger())[0];
    await act(async () => pending.resolve());
    expect(ledger()[before]).toBe("ACKNOWLEDGED");
    expect(context.notify).not.toHaveBeenCalled();
    expect(screen.getByText(/断开请求等待超时/)).toBeTruthy();
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "核对连接状态" })),
    );
    expect(screen.getByText(/原账号尚未确认断开/)).toBeTruthy();
    expect(context.service.disconnect).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    expect(
      (screen.getByRole("button", { name: "查看连接" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(
      (screen.getByRole("button", { name: "断开" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  it("取消并离页、清本机草稿后仍按原请求核对；当前DISCONNECTED不能伪造ACK", async () => {
    const pending = deferred<void>();
    vi.mocked(context.service.disconnect).mockReturnValue(pending.promise);
    const view = await mount();
    await start();
    const original = Object.keys(ledger())[0];
    fireEvent.click(screen.getByRole("button", { name: "取消等待并关闭" }));
    view.unmount();
    clearLocalDrafts();
    vi.mocked(context.service.checkConnection).mockResolvedValue(disconnected);
    await mount();
    fireEvent.click(
      screen.getByRole("button", { name: "核对断开结果（小红书）" }),
    );
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "核对连接状态" })),
    );
    expect(
      screen.getByText(/当前平台显示未连接，但原断开请求回执尚未收到/),
    ).toBeTruthy();
    expect(ledger()[original]).toBe("PENDING");
    expect(context.service.disconnect).toHaveBeenCalledTimes(1);
    expect(context.notify).not.toHaveBeenCalled();
    await act(async () => pending.resolve());
    expect(context.notify).not.toHaveBeenCalled();
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "核对连接状态" })),
    );
    expect(ledger()).toEqual({});
    expect(context.notify).toHaveBeenCalledTimes(1);
  });

  it.each(["account", "user", "platform"])(
    "预检%s变化阻止派发，不断开新对象",
    async (change) => {
      if (change === "account")
        vi.mocked(context.service.checkConnection).mockResolvedValue({
          ...account,
          accountId: "TEST-other",
        });
      if (change === "platform")
        vi.mocked(context.service.checkConnection).mockResolvedValue({
          ...account,
          platform: "douyin",
        });
      if (change === "user")
        vi.mocked(context.service.session).mockResolvedValue({
          authenticated: true,
          userId: "TEST-other",
        });
      await mount();
      await start();
      expect(context.service.disconnect).not.toHaveBeenCalled();
      expect(ledger()).toEqual({});
      expect(screen.getByRole("dialog")).toBeTruthy();
    },
  );

  it("持久记录无法写入时不派发外部断开", async () => {
    await mount();
    const write = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => {
        throw new Error("storage full");
      });
    await start();
    expect(context.service.disconnect).not.toHaveBeenCalled();
    expect(screen.getByText(/操作确认记录暂时无法可靠保存/)).toBeTruthy();
    write.mockRestore();
  });

  it("等待时切换身份，迟到ACK只结算原用户记录且不改变新页面", async () => {
    const pending = deferred<void>();
    vi.mocked(context.service.disconnect).mockReturnValue(pending.promise);
    const view = await mount();
    await start();
    context = {
      ...context,
      session: { authenticated: true, userId: "TEST-other" },
    };
    view.rerender(<ConnectionsPage />);
    await act(async () => pending.resolve());
    expect(Object.values(ledger())).toEqual(["ACKNOWLEDGED"]);
    expect(ledger("TEST-other")).toEqual({});
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(context.notify).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("button", { name: "核对断开结果（小红书）" }),
    ).toBeNull();
  });

  it("核对返回其他账号或失效不能清锁；核对挂起也可取消并保留原记录", async () => {
    await mount();
    await start();
    expect(Object.values(ledger())).toEqual(["ACKNOWLEDGED"]);
    vi.mocked(context.service.checkConnection).mockResolvedValue({
      ...disconnected,
      accountId: "TEST-other",
    });
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "核对连接状态" })),
    );
    expect(screen.getByText(/当前平台返回了其他账号/)).toBeTruthy();
    expect(Object.values(ledger())).toEqual(["ACKNOWLEDGED"]);
    vi.mocked(context.service.checkConnection).mockResolvedValue({
      ...account,
      status: "EXPIRED",
    });
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "核对连接状态" })),
    );
    expect(Object.values(ledger())).toEqual(["ACKNOWLEDGED"]);
    const waiting = deferred<PlatformConnection>();
    vi.mocked(context.service.checkConnection).mockReturnValue(waiting.promise);
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "核对连接状态" })),
    );
    fireEvent.click(screen.getByRole("button", { name: "取消等待并关闭" }));
    await act(async () => waiting.resolve(disconnected));
    expect(context.notify).not.toHaveBeenCalled();
    expect(Object.values(ledger())).toEqual(["ACKNOWLEDGED"]);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
