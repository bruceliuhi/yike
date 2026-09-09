// @vitest-environment jsdom
import {afterEach, describe, expect, it, vi} from "vitest";
import {act, cleanup, fireEvent, render, screen} from "@testing-library/react";
import {AppProvider, useApp} from "../../src/renderer/app/context";
import {service as baseService} from "../../src/renderer/services/client";
import type {Session} from "../../src/renderer/domain/models";

afterEach(() => {cleanup(); vi.useRealTimers();});
function SessionProbe() {
  const {sessionReady, session, refreshSession} = useApp();
  return <>
    <output data-testid="ready">{String(sessionReady)}</output>
    <output data-testid="identity">{session.authenticated ? session.userId : "guest"}</output>
    <button onClick={() => void refreshSession()}>重新确认会话</button>
  </>;
}
describe("initial session lifecycle", () => {
  it("releases initial loading after timeout, ignores the late old identity, and accepts a fresh retry", async () => {
    vi.useFakeTimers();
    let finish!: (value: Session) => void;
    const session = vi.fn()
      .mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}))
      .mockResolvedValue({authenticated: true, userId: "TEST-current-user"});
    render(<AppProvider service={{...baseService, session}}><SessionProbe /></AppProvider>);
    await act(async () => {});
    expect(screen.getByTestId("ready").textContent).toBe("false");
    await act(async () => vi.advanceTimersByTimeAsync(30_000));
    expect(screen.getByTestId("ready").textContent).toBe("true");
    expect(screen.getByText("登录状态确认超时，客户工作空间尚未打开。请重新登录后重试。")).toBeTruthy();
    await act(async () => finish({authenticated: true, userId: "TEST-stale-user"}));
    expect(screen.getByTestId("identity").textContent).toBe("guest");
    await act(async () => fireEvent.click(screen.getByRole("button", {name: "重新确认会话"})));
    expect(screen.getByTestId("identity").textContent).toBe("TEST-current-user");
  });

  it("does not let an older bootstrap timeout reset a newer established session", async () => {
    vi.useFakeTimers();
    let finish!: (value: Session) => void;
    const session = vi.fn()
      .mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}))
      .mockResolvedValue({authenticated: true, userId: "TEST-current-user"});
    render(<AppProvider service={{...baseService, session}}><SessionProbe /></AppProvider>);
    await act(async () => {});
    await act(async () => fireEvent.click(screen.getByRole("button", {name: "重新确认会话"})));
    await act(async () => vi.advanceTimersByTimeAsync(30_000));
    await act(async () => finish({authenticated: true, userId: "TEST-stale-user"}));
    expect(screen.getByTestId("ready").textContent).toBe("true");
    expect(screen.getByTestId("identity").textContent).toBe("TEST-current-user");
    expect(screen.queryByText(/登录状态确认超时/)).toBeNull();
  });
});
