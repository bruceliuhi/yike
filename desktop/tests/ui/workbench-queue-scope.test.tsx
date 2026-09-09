// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AppProvider, useApp } from "../../src/renderer/app/context";
import { TodoQueue } from "../../src/renderer/pages/workbench/TodoQueue";
import type { Session } from "../../src/renderer/domain/models";
import type { YikeService } from "../../src/renderer/services/contracts";
import type { WorkbenchSnapshot } from "../../src/renderer/services/workbench";
const initial: Session = {
  authenticated: true,
  userId: "TEST-same-user",
  accountScope: { id: "TEST-space-A", version: 1 },
};
const changedScopes = [
  { id: "TEST-space-B", version: 1 },
  { id: "TEST-space-A", version: 2 },
];
function snapshot(title: string, targetId: string): WorkbenchSnapshot {
  return {
    queue: "reply",
    items: [
      {
        id: targetId,
        targetId,
        title,
        detail: "TEST 内存待办，未执行客户操作",
        sample: false,
      },
    ],
    total: 1,
  };
}
function SessionControl() {
  const { session, refreshSession } = useApp();
  return (
    <>
      <output>
        {session.accountScope
          ? `${session.accountScope.id}@${session.accountScope.version}`
          : "TEST会话读取中"}
      </output>
      <button onClick={() => void refreshSession()}>TEST刷新会话</button>
      <TodoQueue queue="reply" />
    </>
  );
}
function mount(queue: ReturnType<typeof vi.fn>) {
  let next = initial;
  const service = {
    session: vi.fn(async () => next),
    workbench: { queue },
  } as unknown as YikeService;
  render(
    <AppProvider service={service}>
      <SessionControl />
    </AppProvider>,
  );
  return {
    service,
    switchScope(scope: NonNullable<Session["accountScope"]>) {
      next = { ...initial, accountScope: scope };
      fireEvent.click(screen.getByRole("button", { name: "TEST刷新会话" }));
    },
  };
}
beforeEach(() => {
  history.replaceState(null, "", "#/workbench");
  localStorage.clear();
  sessionStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
it.each(changedScopes)(
  "hides old rows immediately after same-service scope changes to $id v$version",
  async (scope) => {
    let release!: (value: WorkbenchSnapshot) => void;
    const queue = vi
      .fn()
      .mockResolvedValueOnce(snapshot("TEST空间A旧待办", "TEST-old-target"))
      .mockImplementationOnce(
        () =>
          new Promise<WorkbenchSnapshot>((resolve) => {
            release = resolve;
          }),
      );
    const instance = mount(queue);
    expect(
      await screen.findByRole("button", { name: /TEST空间A旧待办/ }),
    ).toBeTruthy();
    instance.switchScope(scope);
    await screen.findByText(`${scope.id}@${scope.version}`);
    expect(
      screen.queryByRole("button", { name: /TEST空间A旧待办/ }),
    ).toBeNull();
    expect(location.hash).toBe("#/workbench");
    await waitFor(() => expect(queue).toHaveBeenCalledTimes(2));
    await act(async () =>
      release(snapshot("TEST当前空间新待办", "TEST-current-target")),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: /TEST当前空间新待办/ }),
    );
    await waitFor(() =>
      expect(location.hash).toBe(
        "#/followups?tab=replies&opportunity=TEST-current-target",
      ),
    );
    expect(instance.service.workbench!.queue).toBe(queue);
  },
);
it.each(changedScopes)(
  "ignores a late old response after same-service scope changes to $id v$version",
  async (scope) => {
    let release!: (value: WorkbenchSnapshot) => void;
    const queue = vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise<WorkbenchSnapshot>((resolve) => {
            release = resolve;
          }),
      )
      .mockResolvedValue(snapshot("TEST当前空间新待办", "TEST-current-target"));
    const instance = mount(queue);
    await waitFor(() => expect(queue).toHaveBeenCalledOnce());
    instance.switchScope(scope);
    await screen.findByText(`${scope.id}@${scope.version}`);
    await act(async () =>
      release(snapshot("TEST空间A迟到待办", "TEST-old-target")),
    );
    expect(
      screen.queryByRole("button", { name: /TEST空间A迟到待办/ }),
    ).toBeNull();
    expect(
      await screen.findByRole("button", { name: /TEST当前空间新待办/ }),
    ).toBeTruthy();
    expect(queue).toHaveBeenCalledTimes(2);
    expect(location.hash).toBe("#/workbench");
  },
);
