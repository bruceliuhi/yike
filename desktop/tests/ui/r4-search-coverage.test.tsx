// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { SearchCoverage } from "../../src/renderer/pages/tasks/SearchCoverage";
import { TasksPage } from "../../src/renderer/pages/Tasks";
import type { AppContextValue } from "../../src/renderer/app/context";
import type { YikeService } from "../../src/renderer/services/contracts";
import type { SearchCoverageQuery } from "../../src/renderer/domain/searchCoverage";
import { parseRoute } from "../../src/renderer/domain/routes";
import { coverageFixture, coverageRun } from "./r4-search-coverage-fixtures";

let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  context = {
    session: {
      authenticated: true,
      userId: "TEST-user",
      accountScope: { id: "TEST-account", version: 1 },
    },
    sessionReady: true,
    route: parseRoute("#/monitors/TEST-task"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
    service: {
      searchCoverage: {
        query: vi.fn(async (request: SearchCoverageQuery) =>
          coverageFixture(request),
        ),
      },
      tasks: vi.fn().mockResolvedValue([coverageRun]),
      openExternal: vi.fn().mockResolvedValue(undefined),
    } as unknown as YikeService,
  };
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
};

it("opens the real P09 coverage tab by default and keeps the original platform/events/config tabs", async () => {
  render(<TasksPage />);
  expect(
    (await screen.findByRole("tab", { name: "搜索覆盖" })).getAttribute(
      "aria-selected",
    ),
  ).toBe("true");
  await screen.findByText("TEST 登录失效，本方向未完成。");
  fireEvent.click(screen.getByRole("tab", { name: "平台状态" }));
  expect(screen.getByRole("region", { name: "平台运行状态" })).toBeTruthy();
  fireEvent.click(screen.getByRole("tab", { name: "任务配置" }));
  expect(screen.getByText("v1")).toBeTruthy();
  expect(screen.getByRole("tab", { name: "执行记录" })).toBeTruthy();
});
it("missing capability or verified session account never requests or fabricates coverage", async () => {
  delete context.service.searchCoverage;
  const view = render(<SearchCoverage run={coverageRun} />);
  await screen.findByText(/搜索覆盖服务尚未接通/);
  const query = vi.fn();
  context = {
    ...context,
    service: { ...context.service, searchCoverage: { query } },
    session: { authenticated: true, userId: "TEST-user" },
  };
  view.rerender(<SearchCoverage run={coverageRun} />);
  await screen.findByText(/尚未提供可核验的账户范围/);
  expect(query).not.toHaveBeenCalled();
  expect(screen.queryByText("已完成")).toBeNull();
});
it("shows the four result types, distinct unknown counts, evidence and exact reconnect route", async () => {
  render(<SearchCoverage run={coverageRun} />);
  await screen.findByText("TEST 登录失效，本方向未完成。");
  expect(screen.getByText(/部分范围尚未完成/)).toBeTruthy();
  for (const label of [
    "访问失败",
    "研究用量已达上限",
    "内容均被排除",
    "已检查范围无合格机会",
  ])
    expect(screen.getAllByText(label).length).toBeGreaterThan(0);
  expect(screen.getAllByText("未知").length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole("button", { name: "重新连接" }));
  expect(context.navigate).toHaveBeenCalledWith(
    "/connections?connect=xhs&returnTo=%2Fmonitors%2FTEST-task",
  );
  fireEvent.click(
    screen.getByRole("button", { name: "查看TEST 替换服务商覆盖明细" }),
  );
  fireEvent.click(screen.getByText("TEST 不符合画像"));
  expect(screen.getByText("TEST 仅用于覆盖显示的合成公开内容。")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "打开原始来源" }));
  await waitFor(() =>
    expect(context.service.openExternal).toHaveBeenCalledWith(
      "https://example.com/TEST-source",
    ),
  );
});
it("requires exact response identity and preserves an error with retry instead of empty success", async () => {
  context.service.searchCoverage!.query = vi.fn(async (request) => ({
    ...coverageFixture(request),
    accountScopeId: "OTHER",
  }));
  render(<SearchCoverage run={coverageRun} />);
  await screen.findByText(/当前账户、任务或画像版本不一致/);
  expect(screen.queryByText("TEST 登录失效，本方向未完成。")).toBeNull();
  context.service.searchCoverage!.query = vi.fn(async (request) =>
    coverageFixture(request),
  );
  fireEvent.click(screen.getByRole("button", { name: "重试" }));
  await screen.findByText("TEST 登录失效，本方向未完成。");
});
it("bounds hanging reads and ignores late responses after timeout and retry", async () => {
  vi.useFakeTimers();
  const pending = deferred<ReturnType<typeof coverageFixture>>();
  let request!: SearchCoverageQuery;
  context.service.searchCoverage!.query = vi.fn((q) => {
    request = q;
    return pending.promise;
  });
  render(<SearchCoverage run={coverageRun} />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(30_001);
  });
  expect(screen.getByText(/搜索覆盖读取超时/)).toBeTruthy();
  await act(async () => {
    pending.resolve(coverageFixture(request));
  });
  expect(screen.queryByText("TEST 登录失效，本方向未完成。")).toBeNull();
  context.service.searchCoverage!.query = vi.fn(async (q) =>
    coverageFixture(q),
  );
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
  });
  expect(screen.getByText("TEST 登录失效，本方向未完成。")).toBeTruthy();
});
it.each(["account", "profile", "user"] as const)(
  "discards an old response after a %s change",
  async (kind) => {
    const pending = deferred<ReturnType<typeof coverageFixture>>();
    let original!: SearchCoverageQuery;
    context.service.searchCoverage!.query = vi.fn((q) => {
      original = q;
      return pending.promise;
    });
    const view = render(<SearchCoverage run={coverageRun} />);
    await waitFor(() => expect(original).toBeTruthy());
    context = {
      ...context,
      session: {
        ...context.session,
        ...(kind === "user"
          ? { userId: "TEST-new-user" }
          : kind === "account"
            ? { accountScope: { id: "TEST-new-account", version: 2 } }
            : {}),
      },
      service: {
        ...context.service,
        searchCoverage: {
          query: vi.fn(async (q) => {
            const value = coverageFixture(q);
            value.units[0].explanation = "TEST 新上下文数据";
            return value;
          }),
        },
      },
    };
    view.rerender(
      <SearchCoverage
        run={
          kind === "profile"
            ? { ...coverageRun, profileVersion: 2 }
            : coverageRun
        }
      />,
    );
    await screen.findByText("TEST 新上下文数据");
    await act(async () => {
      pending.resolve(coverageFixture(original));
    });
    expect(screen.queryByText("TEST 登录失效，本方向未完成。")).toBeNull();
  },
);
it("keeps expired snapshots readable but disables related actions", async () => {
  context.service.searchCoverage!.query = vi.fn(async (request) => {
    const value = coverageFixture(request);
    value.generatedAt = "2020-01-01T00:00:00Z";
    value.expiresAt = "2020-01-02T00:00:00Z";
    return value;
  });
  render(<SearchCoverage run={coverageRun} />);
  await screen.findByText(/覆盖快照已过期/);
  expect(
    (screen.getByRole("button", { name: "重新连接" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  expect(screen.getByText("TEST 登录失效，本方向未完成。")).toBeTruthy();
});
it("expires a displayed snapshot without a page refresh", async () => {
  vi.useFakeTimers();
  context.service.searchCoverage!.query = vi.fn(async (request) => {
    const value = coverageFixture(request);
    value.expiresAt = new Date(Date.now() + 1000).toISOString();
    return value;
  });
  render(<SearchCoverage run={coverageRun} />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(10);
  });
  expect(
    (screen.getByRole("button", { name: "重新连接" }) as HTMLButtonElement)
      .disabled,
  ).toBe(false);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1001);
  });
  expect(screen.getByText(/覆盖快照已过期/)).toBeTruthy();
  expect(
    (screen.getByRole("button", { name: "重新连接" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
});
it("does not accept coverage for unconfigured platforms or query a task without a profile binding", async () => {
  const view = render(
    <SearchCoverage run={{ ...coverageRun, platforms: ["web"] }} />,
  );
  await screen.findByText(/超出当前任务的平台范围/);
  const query = vi.fn();
  context = {
    ...context,
    service: { ...context.service, searchCoverage: { query } },
  };
  view.rerender(
    <SearchCoverage run={{ ...coverageRun, profileVersion: undefined }} />,
  );
  await screen.findByText(/缺少已确认画像版本/);
  expect(query).not.toHaveBeenCalled();
});
it("does not replace a remounted page with a response from the page that was left", async () => {
  const pending = deferred<ReturnType<typeof coverageFixture>>();
  let original!: SearchCoverageQuery;
  context.service.searchCoverage!.query = vi.fn((q) => {
    original = q;
    return pending.promise;
  });
  const old = render(<SearchCoverage run={coverageRun} />);
  await waitFor(() => expect(original).toBeTruthy());
  old.unmount();
  context.service.searchCoverage!.query = vi.fn(async (q) => {
    const value = coverageFixture(q);
    value.units[0].explanation = "TEST 重入数据";
    return value;
  });
  render(<SearchCoverage run={coverageRun} />);
  await screen.findByText("TEST 重入数据");
  await act(async () => {
    pending.resolve(coverageFixture(original));
  });
  expect(screen.queryByText("TEST 登录失效，本方向未完成。")).toBeNull();
});
it("terminal runs offer a new draft plan while unknown recovery cannot be retried as execution", async () => {
  context.service.searchCoverage!.query = vi.fn(async (request) => {
    const value = coverageFixture(request);
    value.units[1].recovery = "TERMINAL";
    return value;
  });
  const onPlan = vi.fn();
  render(<SearchCoverage run={coverageRun} onPlan={onPlan} />);
  fireEvent.click(
    await screen.findByRole("button", { name: "查看TEST 方案比较覆盖明细" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "基于未查范围创建草稿" }));
  await waitFor(() =>
    expect(onPlan).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "NEW_DRAFT", userId: "TEST-user" }),
    ),
  );
  context.service.searchCoverage!.query = vi.fn(async (request) => {
    const value = coverageFixture(request);
    value.units[1].recovery = "UNKNOWN";
    return value;
  });
  fireEvent.click(screen.getByRole("button", { name: "刷新覆盖" }));
  fireEvent.click(
    await screen.findByRole("button", { name: "查看TEST 方案比较覆盖明细" }),
  );
  expect(
    screen.queryByRole("button", { name: "基于未查范围创建草稿" }),
  ).toBeNull();
  expect(screen.getByText(/当前可恢复状态或搜贝版本尚未确认/)).toBeTruthy();
});
it("opens a typed limit preview only for confirmed resumability, never executes or settles", async () => {
  context.service.searchCoverage!.query = vi.fn(async (request) => {
    const value = coverageFixture(request);
    value.usage = {
      unit: "SOUBEI",
      ruleVersion: "TEST-rule",
      budgetRevision: 3,
      estimated: 15,
      maximum: 20,
      actual: null,
      settlement: "UNKNOWN",
    };
    return value;
  });
  const onPlan = vi.fn();
  render(<SearchCoverage run={coverageRun} onPlan={onPlan} />);
  fireEvent.click(
    await screen.findByRole("button", { name: "查看TEST 方案比较覆盖明细" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "调整搜贝上限" }));
  await waitFor(() =>
    expect(onPlan).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: "ADJUST_LIMIT",
        runId: "TEST-run",
        taskId: "TEST-task",
        windowId: "TEST-window",
        accountScopeId: "TEST-account",
        budgetRevision: 3,
      }),
    ),
  );
  const usage = within(screen.getByRole("region", { name: "本次搜贝用量" }));
  expect(usage.getByText("未知 搜贝")).toBeTruthy();
  expect(context.navigate).not.toHaveBeenCalled();
});
