// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { OpportunityBrief } from "../../src/renderer/pages/workbench/OpportunityBrief";
import { WorkbenchPage } from "../../src/renderer/pages/Workbench";
import type { AppContextValue } from "../../src/renderer/app/context";
import type { YikeService } from "../../src/renderer/services/contracts";
import type { BriefQuery } from "../../src/renderer/domain/opportunityBrief";
import { parseRoute } from "../../src/renderer/domain/routes";
import { briefFixture, briefProfile } from "./r4-opportunity-brief-fixtures";
let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
const props = () => ({
  profiles: [briefProfile],
  profilesLoading: false,
  profilesError: "",
  onProfilesRetry: vi.fn(),
  connections: [],
  connectionsLoading: false,
  connectionsError: "",
  onConnectionsRetry: vi.fn(),
});
beforeEach(() => {
  context = {
    session: {
      authenticated: true,
      userId: "TEST-user",
      accountScope: { id: "TEST-account", version: 1 },
    },
    sessionReady: true,
    route: parseRoute("#/workbench"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
    service: {
      opportunityBrief: {
        query: vi.fn(async (request: BriefQuery) => briefFixture(request)),
      },
      profiles: vi.fn().mockResolvedValue([briefProfile]),
      connections: vi.fn().mockResolvedValue([]),
      tasks: vi.fn().mockResolvedValue([]),
      opportunities: vi.fn().mockResolvedValue([]),
    } as unknown as YikeService,
  };
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
const pending = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { resolve, promise };
};

it("renders three groups, their source basis and exact existing destinations without a business mutation", async () => {
  render(<OpportunityBrief {...props()} />);
  await screen.findByText("TEST 客户机会");
  fireEvent.click(screen.getByText("查看判断依据"));
  expect(screen.getByText("TEST 本段为隔离测试的已核验内容。")).toBeTruthy();
  expect(document.body.textContent).not.toMatch(/Asia\/Shanghai|America\/|Europe\/|（UTC）|记录 TEST/);
  expect(document.body.textContent).not.toContain('画像 v');
  fireEvent.click(screen.getByRole("button", { name: "查看机会证据" }));
  expect(context.navigate).toHaveBeenLastCalledWith(
    "/opportunities/TEST-opportunity",
  );
  fireEvent.click(screen.getByRole("tab", { name: /重要变化/ }));
  expect(screen.getByText("TEST 重要变化")).toBeTruthy();
  expect(screen.getByText(/留存来源证据/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'查看机会证据'}));
  expect(context.navigate).toHaveBeenLastCalledWith('/opportunities/TEST-opportunity?tab=changes');
  fireEvent.click(screen.getByRole("tab", { name: /待跟进/ }));
  fireEvent.click(screen.getByRole("button", { name: "查看该商机跟进" }));
  expect(context.navigate).toHaveBeenLastCalledWith(
    "/followups?tab=todo&opportunity=TEST-opportunity",
  );
});
it("retains old todo and sample entries on the real workbench page", async () => {
  render(<WorkbenchPage />);
  await screen.findByText("TEST 客户机会");
  fireEvent.click(screen.getByText("全部待办与准备步骤"));
  expect(screen.getByRole("tab", { name: "待复核" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /180㎡高交会/ }));
  expect(context.navigate).toHaveBeenLastCalledWith("/opportunities/sample");
});
it("missing capability, missing verified scope and missing confirmed profile do not fabricate a briefing", async () => {
  delete context.service.opportunityBrief;
  const view = render(<OpportunityBrief {...props()} />);
  await screen.findByText(/机会简报服务尚未接通/);
  context = {
    ...context,
    service: { ...context.service, opportunityBrief: { query: vi.fn() } },
    session: { authenticated: true, userId: "TEST-user" },
  };
  view.rerender(<OpportunityBrief {...props()} />);
  await screen.findByText(/尚未提供可核验的账户范围/);
  expect(context.service.opportunityBrief!.query).not.toHaveBeenCalled();
  view.rerender(<OpportunityBrief {...props()} profiles={[]} />);
  await screen.findByText("先确认业务画像");
});
it("keeps no-check, partial and truly empty complete snapshots distinct", async () => {
  const query = vi.fn(async (request: BriefQuery) => {
    const value = briefFixture(request);
    value.coverage = "PARTIAL";
    value.uncheckedScope = ["TEST 未检查平台"];
    for (const group of Object.values(value.groups)) {
      group.items = [];
      group.total = 0;
    }
    return value;
  });
  context.service.opportunityBrief!.query = query;
  render(<OpportunityBrief {...props()} />);
  await screen.findByText("已完成部分暂未列出事项");
  expect(screen.queryByText(/本次已查范围暂无/)).toBeNull();
  context.service.opportunityBrief!.query = vi.fn(async (request) => {
    const value = briefFixture(request);
    for (const group of Object.values(value.groups)) {
      group.items = [];
      group.total = 0;
    }
    return value;
  });
  fireEvent.click(screen.getByRole("button", { name: "刷新简报" }));
  await screen.findByText("本次已查范围暂无已复核的客户机会");
  context.service.opportunityBrief!.query = vi.fn(async (request) => {
    const value = briefFixture(request);
    value.coverage = "NOT_CHECKED";
    value.checkedScope = [];
    value.runs = [];
    value.lastCompletedCheckAt = null;
    for (const group of Object.values(value.groups)) {
      group.items = [];
      group.total = 0;
    }
    return value;
  });
  fireEvent.click(screen.getByRole("button", { name: "刷新简报" }));
  await screen.findByText("尚未完成检查");
  expect(screen.queryByText(/本次已查范围暂无/)).toBeNull();
});
it("rejects stale identity data and does not flash it after profile selection", async () => {
  const old = pending<ReturnType<typeof briefFixture>>();
  let original!: BriefQuery;
  context.service.opportunityBrief!.query = vi.fn((request) => {
    original = request;
    return old.promise;
  });
  const newer = { ...briefProfile, id: "TEST-profile-2", version: 2 };
  render(<OpportunityBrief {...props()} profiles={[briefProfile, newer]} />);
  await waitFor(() => expect(original).toBeTruthy());
  context.service.opportunityBrief!.query = vi.fn(async (request) => {
    const value = briefFixture(request);
    value.groups.contact.items[0].title = "TEST 新画像的简报";
    return value;
  });
  fireEvent.change(screen.getByRole("combobox", { name: "简报业务画像" }), {
    target: { value: briefProfile.id },
  });
  await screen.findByText("TEST 新画像的简报");
  await act(async () => old.resolve(briefFixture(original)));
  expect(screen.queryByText("TEST 客户机会")).toBeNull();
});
it("bounds hanging reads, ignores a late result and permits a fresh retry", async () => {
  vi.useFakeTimers();
  const old = pending<ReturnType<typeof briefFixture>>();
  let original!: BriefQuery;
  context.service.opportunityBrief!.query = vi.fn((request) => {
    original = request;
    return old.promise;
  });
  render(<OpportunityBrief {...props()} />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(30_001);
  });
  expect(screen.getByText(/机会简报读取超时/)).toBeTruthy();
  await act(async () => old.resolve(briefFixture(original)));
  expect(screen.queryByText("TEST 客户机会")).toBeNull();
  context.service.opportunityBrief!.query = vi.fn(async (request) =>
    briefFixture(request),
  );
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
  });
  expect(screen.getByText("TEST 客户机会")).toBeTruthy();
});
it("does not navigate unavailable targets and disables expired summaries", async () => {
  context.service.opportunityBrief!.query = vi.fn(async (request) => {
    const value = briefFixture(request);
    value.groups.contact.items[0].validity = "TARGET_MISSING";
    return value;
  });
  render(<OpportunityBrief {...props()} />);
  await screen.findByText("目标已不可用");
  expect(
    (screen.getByRole("button", { name: "查看机会证据" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  context.service.opportunityBrief!.query = vi.fn(async (request) => {
    const value = briefFixture(request);
    value.generatedAt = "2020-01-01T00:00:00Z";
    value.lastCompletedCheckAt = value.generatedAt;
    value.expiresAt = "2020-01-02T00:00:00Z";
    for (const group of Object.values(value.groups))
      for (const item of group.items) item.basis.verifiedAt = value.generatedAt;
    return value;
  });
  fireEvent.click(screen.getByRole("button", { name: "刷新简报" }));
  await screen.findByText(/简报已过期/);
  expect(
    (screen.getByRole("button", { name: "查看机会证据" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  expect(context.navigate).not.toHaveBeenCalled();
});
it("rejects a mismatched date and recovers on retry without claiming zero results", async () => {
  context.service.opportunityBrief!.query = vi.fn(async (request) => ({
    ...briefFixture(request),
    businessDate: "2000-01-01",
  }));
  render(<OpportunityBrief {...props()} />);
  await screen.findByText(/业务日期不一致/);
  expect(screen.queryByText(/本次已查范围暂无/)).toBeNull();
  context.service.opportunityBrief!.query = vi.fn(async (request) =>
    briefFixture(request),
  );
  fireEvent.click(screen.getByRole("button", { name: "重试" }));
  await screen.findByText("TEST 客户机会");
});
it.each(["user", "account"] as const)(
  "discards a previous %s's late briefing",
  async (kind) => {
    const old = pending<ReturnType<typeof briefFixture>>();
    let original!: BriefQuery;
    context.service.opportunityBrief!.query = vi.fn((request) => {
      original = request;
      return old.promise;
    });
    const view = render(<OpportunityBrief {...props()} />);
    await waitFor(() => expect(original).toBeTruthy());
    context = {
      ...context,
      session: {
        ...context.session,
        ...(kind === "user"
          ? { userId: "TEST-new-user" }
          : { accountScope: { id: "TEST-new-account", version: 2 } }),
      },
      service: {
        ...context.service,
        opportunityBrief: {
          query: vi.fn(async (request) => {
            const value = briefFixture(request);
            value.groups.contact.items[0].title = "TEST 当前账户简报";
            return value;
          }),
        },
      },
    };
    view.rerender(<OpportunityBrief {...props()} />);
    await screen.findByText("TEST 当前账户简报");
    await act(async () => old.resolve(briefFixture(original)));
    expect(screen.queryByText("TEST 客户机会")).toBeNull();
  },
);
it("paginates complete snapshot rows without navigating to an unrelated target", async () => {
  context.service.opportunityBrief!.query = vi.fn(async (request) => {
    const value = briefFixture(request);
    const row = value.groups.contact.items[0];
    value.groups.contact = {
      total: 7,
      items: Array.from({ length: 7 }, (_, index) => ({
        ...row,
        id: `TEST-row-${index}`,
        opportunityId: `TEST-opportunity-${index}`,
        title: `TEST 机会 ${index}`,
      })),
    };
    return value;
  });
  render(<OpportunityBrief {...props()} />);
  await screen.findByText("TEST 机会 0");
  expect(screen.queryByText("TEST 机会 6")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  expect(screen.getByText("TEST 机会 6")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "查看机会证据" }));
  expect(context.navigate).toHaveBeenLastCalledWith(
    "/opportunities/TEST-opportunity-6",
  );
});
