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
import { TodoQueue } from "../../src/renderer/pages/workbench/TodoQueue";
import { CandidatesPage } from "../../src/renderer/pages/Opportunities";
import { WorkbenchPage } from "../../src/renderer/pages/Workbench";
import { parseRoute } from "../../src/renderer/domain/routes";
import {
  parseWorkbenchSnapshot,
  type WorkbenchQueue,
} from "../../src/renderer/services/workbench";
import type { AppContextValue } from "../../src/renderer/app/context";
import type { YikeService } from "../../src/renderer/services/contracts";
import { candidate, profile, opportunity } from "../visual/fixtures";
let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
const item = {
  id: "TEST-todo",
  targetId: "TEST-target",
  title: "TEST 需求复核",
  detail: "TEST 原文待核对",
  sample: false as const,
};
beforeEach(() => {
  context = {
    session: { authenticated: true, userId: crypto.randomUUID() },
    service: {
      workbench: { queue: vi.fn() },
      candidates: vi.fn(),
      profiles: vi.fn().mockResolvedValue([profile]),
    } as unknown as YikeService,
    route: parseRoute("#/workbench"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
  };
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
it.each(["review", "contact", "reply", "followup"] as WorkbenchQueue[])(
  "loads %s and preserves the exact target in its destination",
  async (queue) => {
    vi.mocked(context.service.workbench!.queue).mockResolvedValue({
      queue,
      items: [item],
      total: 1,
    });
    render(<TodoQueue queue={queue} />);
    fireEvent.click(
      await screen.findByRole("button", { name: /TEST 需求复核/ }),
    );
    const expected = {
      review: "/candidates?candidate=TEST-target",
      contact: "/outreach?opportunity=TEST-target",
      reply: "/followups?tab=replies&opportunity=TEST-target",
      followup: "/followups?tab=todo&opportunity=TEST-target",
    };
    expect(context.navigate).toHaveBeenCalledWith(expected[queue]);
  },
);
it("shows an empty queue only after a complete authoritative empty response", async () => {
  let resolve!: (v: any) => void;
  vi.mocked(context.service.workbench!.queue).mockImplementationOnce(
    () => new Promise((r) => (resolve = r)),
  );
  render(<TodoQueue queue="review" />);
  expect(screen.queryByText("还没有待处理商机")).toBeNull();
  await waitFor(() =>
    expect(context.service.workbench!.queue).toHaveBeenCalledOnce(),
  );
  await act(async () => resolve({ queue: "review", items: [], total: 0 }));
  expect(screen.getByText("还没有待处理商机")).toBeTruthy();
});
it("does not reuse a late result after switching queues", async () => {
  let resolve!: (v: any) => void;
  vi.mocked(context.service.workbench!.queue)
    .mockImplementationOnce(() => new Promise((r) => (resolve = r)))
    .mockResolvedValue({ queue: "reply", items: [], total: 0 });
  const view = render(<TodoQueue queue="review" />);
  await waitFor(() =>
    expect(context.service.workbench!.queue).toHaveBeenCalledOnce(),
  );
  view.rerender(<TodoQueue queue="reply" />);
  await screen.findByText("还没有待处理商机");
  await act(async () => resolve({ queue: "review", items: [item], total: 1 }));
  expect(screen.queryByText(item.title)).toBeNull();
});
it("rejects wrong queue, duplicate records, partial snapshots and sample targets", () => {
  for (const value of [
    { queue: "reply", items: [], total: 0 },
    { queue: "review", items: [item, item], total: 2 },
    { queue: "review", items: [], total: 1 },
    { queue: "review", items: [{ ...item, sample: true }], total: 1 },
    { queue: "review", items: [{ ...item, targetId: "sample" }], total: 1 },
  ])
    expect(() => parseWorkbenchSnapshot(value, "review")).toThrow();
});
it("retrieves the exact candidate from a todo link rather than the first list row", async () => {
  context.route = parseRoute("#/candidates?candidate=TEST-candidate");
  vi.mocked(context.service.candidates).mockResolvedValue({
    items: [candidate],
    total: 1,
    page: 1,
    pageSize: 10,
  });
  render(<CandidatesPage />);
  await screen.findByText("当前仅查看待办关联的线索。");
  await waitFor(() =>
    expect(context.service.candidates).toHaveBeenCalledWith({
      ids: ["TEST-candidate"],
      page: 1,
      pageSize: 10,
    }),
  );
  expect(screen.getByRole("button", { name: "查看全部线索" })).toBeTruthy();
  expect(
    (
      screen.getByRole("combobox", {
        name: "候选来源筛选",
      }) as HTMLSelectElement
    ).disabled,
  ).toBe(true);
});
it("does not display a different candidate returned for a todo target", async () => {
  context.route = parseRoute("#/candidates?candidate=TEST-candidate");
  vi.mocked(context.service.candidates).mockResolvedValue({
    items: [{ ...candidate, id: "wrong" }],
    total: 1,
    page: 1,
    pageSize: 10,
  });
  render(<CandidatesPage />);
  await screen.findByText("返回线索与待办目标不匹配，请刷新重试。");
  expect(screen.queryByRole("region", { name: "原始线索列表" })).toBeNull();
});
it("clears the old selection and confirmation when a todo target changes", async () => {
  context.route = parseRoute("#/candidates?candidate=TEST-candidate");
  vi.mocked(context.service.candidates).mockImplementation(async (query) => ({
    items: [{ ...candidate, id: query!.ids![0] }],
    total: 1,
    page: 1,
    pageSize: 10,
  }));
  const view = render(<CandidatesPage />);
  fireEvent.click(
    await screen.findByRole("checkbox", { name: `选择候选${candidate.title}` }),
  );
  fireEvent.click(screen.getByRole("button", { name: "批量确认入库（1）" }));
  await screen.findByRole("dialog", { name: "确认候选入库" });
  context = {
    ...context,
    route: parseRoute("#/candidates?candidate=TEST-next"),
  };
  view.rerender(<CandidatesPage />);
  await waitFor(() =>
    expect(context.service.candidates).toHaveBeenLastCalledWith({
      ids: ["TEST-next"],
      page: 1,
      pageSize: 10,
    }),
  );
  expect(screen.queryByRole("dialog", { name: "确认候选入库" })).toBeNull();
  expect(
    (
      screen.getByRole("checkbox", {
        name: `选择候选${candidate.title}`,
      }) as HTMLInputElement
    ).checked,
  ).toBe(false);
  expect(
    screen.getByRole("button", { name: "批量确认入库（0）" }),
  ).toBeTruthy();
});
it("times out a stalled candidate target without substituting a different row", async () => {
  vi.useFakeTimers();
  context.route = parseRoute("#/candidates?candidate=TEST-candidate");
  vi.mocked(context.service.candidates).mockImplementation(
    () => new Promise(() => {}),
  );
  render(<CandidatesPage />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(30001);
  });
  expect(screen.getByText("线索读取超时，请重试。")).toBeTruthy();
  expect(screen.queryByRole("region", { name: "原始线索列表" })).toBeNull();
});
it("shows an explicit missing target state", async () => {
  context.route = parseRoute("#/candidates?candidate=missing");
  vi.mocked(context.service.candidates).mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    pageSize: 10,
  });
  render(<CandidatesPage />);
  expect(await screen.findByText("未找到待办关联的线索")).toBeTruthy();
});
it("excludes public samples from the legacy customer opportunity fallback", async () => {
  context.service.workbench = undefined;
  context.service.opportunities = vi.fn().mockResolvedValue([
    opportunity,
    { ...opportunity, id: "sample", title: "TEST hidden sample ID" },
    {
      ...opportunity,
      id: "TEST-sample",
      sample: true,
      title: "TEST hidden sample flag",
    },
  ]);
  context.service.connections = vi.fn().mockResolvedValue([]);
  context.service.tasks = vi.fn().mockResolvedValue([]);
  render(<WorkbenchPage />);
  fireEvent.click(screen.getByText("全部待办与准备步骤"));
  fireEvent.click(screen.getByRole("tab", { name: "待联系" }));
  expect(
    await screen.findByRole("button", { name: new RegExp(opportunity.title) }),
  ).toBeTruthy();
  expect(screen.queryByText("TEST hidden sample ID")).toBeNull();
  expect(screen.queryByText("TEST hidden sample flag")).toBeNull();
});
