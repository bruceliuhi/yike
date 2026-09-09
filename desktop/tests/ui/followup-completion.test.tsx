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
import { FollowupsPage } from "../../src/renderer/pages/Followups";
import { PUBLIC_SAMPLE } from "../../src/renderer/pages/Opportunities";
import { parseRoute } from "../../src/renderer/domain/routes";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { operationLedgerKey } from "../../src/renderer/app/operationLedger";
import {
  followupKey,
  type FollowupRecord,
  type FollowupReceipt,
  type LinkedReply,
} from "../../src/renderer/domain/followup";
import type { AppContextValue } from "../../src/renderer/app/context";
import type { YikeService } from "../../src/renderer/services/contracts";
let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
const opportunity = {
  ...PUBLIC_SAMPLE,
  id: "TEST-opp",
  sample: false,
  title: "TEST商机",
  profileVersionId: "TEST-profile-v1",
  updatedAt: "2026-09-09T09:00:00Z",
};
const row = (change: Partial<FollowupRecord> = {}): FollowupRecord => ({
  id: "TEST-f1",
  opportunityId: opportunity.id,
  profileVersionId: opportunity.profileVersionId,
  revision: 1,
  title: opportunity.title,
  status: "CONTACTED",
  note: "TEST原沟通",
  createdAt: "2026-09-09T09:00:00Z",
  occurredAt: "2026-09-08T08:00:00Z",
  nextStep: "TEST准备资料",
  nextFollowupAt: "2030-01-01T09:00:00Z",
  ownerId: "TEST-member",
  ownerName: "TEST成员",
  state: "ACTIVE",
  kind: "manual",
  sample: false,
  ...change,
});
const reply = (change: Partial<LinkedReply> = {}): LinkedReply => ({
  id: "TEST-reply",
  revision: 1,
  opportunityId: opportunity.id,
  profileVersionId: opportunity.profileVersionId,
  sendRequestId: "TEST-send",
  platform: "TEST渠道",
  content: "TEST真实条件回复",
  receivedAt: "2026-09-09T09:00:00Z",
  read: false,
  sample: false,
  ...change,
});
const ledger = () =>
  operationLedgerKey("followup-operations", context.session.userId!);
const stored = () => JSON.parse(localStorage.getItem(ledger()) || "{}");
function mockRecords(records = [row()]) {
  vi.mocked(context.service.followup!.list).mockResolvedValue({
    records,
    members: [
      { id: "TEST-member", name: "TEST成员" },
      { id: "OTHER", name: "另一成员" },
    ],
  });
}
function addRoute() {
  context.route = parseRoute("#/followups?add=1");
}
async function fill() {
  await screen.findByRole("option", { name: "TEST商机" });
  fireEvent.change(screen.getByRole("combobox", { name: "关联商机" }), {
    target: { value: "TEST-opp" },
  });
  fireEvent.click(screen.getByRole("radio", { name: "已联系" }));
  fireEvent.change(screen.getByRole("textbox", { name: "跟进备注" }), {
    target: { value: "TEST人工记录" },
  });
}
async function selectManual() {
  fireEvent.click(await screen.findByRole("button", { name: "TEST商机" }));
  fireEvent.click(screen.getByRole("tab", { name: "人工登记" }));
}
beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  context = {
    service: {
      opportunities: vi.fn().mockResolvedValue([opportunity, PUBLIC_SAMPLE]),
      followups: vi.fn().mockResolvedValue([]),
      addFollowup: vi.fn().mockResolvedValue(undefined),
      followup: {
        list: vi.fn(),
        replies: vi.fn().mockResolvedValue([]),
        mutate: vi.fn(),
        operation: vi.fn(),
      },
    } as unknown as YikeService,
    session: { authenticated: true, userId: "TEST-member" },
    route: parseRoute("#/followups"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
  };
  mockRecords();
});
afterEach(() => {
  cleanup();
  act(() => clearLocalDrafts());
  vi.useRealTimers();
});
describe("P14 structured followup lists and replies", () => {
  it("honors a workbench target once, selects its latest record, and does not pull back a local selection on refresh", async () => {
    context.route = parseRoute("#/followups?opportunity=TEST-opp&tab=replies");
    mockRecords([
      row({
        id: "old",
        title: "TEST旧登记",
        createdAt: "2020-01-01T09:00:00Z",
      }),
      row({ id: "latest", title: "TEST最新登记" }),
      row({ id: "other", opportunityId: "OTHER", title: "其他客户" }),
    ]);
    render(<FollowupsPage />);
    const latest = await screen.findByRole("button", { name: "TEST最新登记" });
    await waitFor(() =>
      expect(latest.closest("tr")?.className).toBe("selected"),
    );
    expect(
      screen
        .getByRole("tab", { name: "回复记录" })
        .getAttribute("aria-selected"),
    ).toBe("true");
    fireEvent.click(screen.getByRole("tab", { name: "全部" }));
    fireEvent.click(screen.getByRole("button", { name: "其他客户" }));
    fireEvent.click(screen.getByRole("button", { name: "刷新" }));
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "其他客户" }).closest("tr")
          ?.className,
      ).toBe("selected"),
    );
    expect(
      screen.getByRole("tab", { name: "全部" }).getAttribute("aria-selected"),
    ).toBe("true");
  });
  it("reports a missing workbench target without selecting another customer", async () => {
    context.route = parseRoute("#/followups?opportunity=missing&tab=todo");
    render(<FollowupsPage />);
    await screen.findByText(
      "未找到目标商机的跟进记录，请核对商机是否已登记或仍可访问。",
    );
    expect(
      screen.getByRole("button", { name: "TEST商机" }).closest("tr")?.className,
    ).not.toBe("selected");
  });
  it("filters owners and dates and distinguishes all from planned followups", async () => {
    mockRecords([
      row(),
      row({
        id: "TEST-f2",
        title: "其他商机",
        ownerId: "OTHER",
        ownerName: "另一成员",
        nextFollowupAt: null,
      }),
    ]);
    render(<FollowupsPage />);
    await screen.findByRole("button", { name: "TEST商机" });
    expect(screen.queryByRole("button", { name: "其他商机" })).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "全部" }));
    expect(screen.getByRole("button", { name: "其他商机" })).toBeTruthy();
    fireEvent.change(screen.getByRole("combobox", { name: "筛选负责人" }), {
      target: { value: "OTHER" },
    });
    expect(screen.queryByRole("button", { name: "TEST商机" })).toBeNull();
    fireEvent.change(screen.getByLabelText("筛选记录日期"), {
      target: { value: "2000-01-01" },
    });
    expect(screen.getByText("没有符合筛选的记录")).toBeTruthy();
  });
  it("filters the displayed local calendar day rather than the stored UTC date", async () => {
    const shortlyAfterMidnight = new Date(2026, 8, 9, 0, 30).toISOString();
    mockRecords([row({ occurredAt: shortlyAfterMidnight })]);
    render(<FollowupsPage />);
    await screen.findByRole("button", { name: "TEST商机" });
    fireEvent.change(screen.getByLabelText("筛选记录日期"), {
      target: { value: "2026-09-09" },
    });
    expect(screen.getByRole("button", { name: "TEST商机" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("筛选记录日期"), {
      target: { value: "2026-09-08" },
    });
    expect(screen.queryByRole("button", { name: "TEST商机" })).toBeNull();
  });
  it("excludes same-opportunity samples from the customer manual timeline", async () => {
    mockRecords([
      row(),
      row({
        id: "TEST-sample",
        sample: true,
        note: "TEST样例不能混入客户时间线",
      }),
    ]);
    render(<FollowupsPage />);
    await selectManual();
    expect(screen.getByText("TEST原沟通")).toBeTruthy();
    expect(screen.queryByText("TEST样例不能混入客户时间线")).toBeNull();
  });
  it("does not treat a failed service as an empty list and supports refresh", async () => {
    vi.mocked(context.service.followup!.list).mockRejectedValueOnce(
      new Error("TEST列表失败"),
    );
    render(<FollowupsPage />);
    await screen.findByText("TEST列表失败");
    expect(screen.queryByText("暂无跟进记录")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "刷新" }));
    await screen.findByRole("button", { name: "TEST商机" });
  });
  it("rejects duplicate identities and never renders their actions", async () => {
    mockRecords([row(), row()]);
    render(<FollowupsPage />);
    await screen.findByText("服务返回重复记录，请刷新核对。");
    expect(screen.queryByRole("button", { name: "TEST商机" })).toBeNull();
  });
  it("loads associated channel replies with their sending record and read state", async () => {
    vi.mocked(context.service.followup!.replies).mockImplementation(
      async (id) => (id ? [reply()] : []),
    );
    render(<FollowupsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "TEST商机" }));
    await screen.findByText("TEST真实条件回复");
    expect(screen.getByText("关联发送记录：TEST-send")).toBeTruthy();
    expect(screen.getByText("未读")).toBeTruthy();
    vi.mocked(context.service.followup!.mutate).mockImplementation(
      async (input) => ({
        binding: input.binding,
        status: "SUCCEEDED",
        confirmed: true,
        reply: reply({ revision: 2, read: true }),
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "标为已读" }));
    await waitFor(() =>
      expect(context.service.followup!.mutate).toHaveBeenCalledOnce(),
    );
    expect(
      vi.mocked(context.service.followup!.mutate).mock.calls[0][0].binding,
    ).toMatchObject({
      action: "mark-read",
      targetId: "TEST-reply",
      targetRevision: 1,
    });
  });
  it("shows unmatched replies without enabling writes or inventing an association", async () => {
    vi.mocked(context.service.followup!.replies).mockResolvedValue([
      reply({
        opportunityId: null,
        profileVersionId: null,
        sendRequestId: null,
        unmatchedReason: "TEST未匹配",
      }),
    ]);
    render(<FollowupsPage />);
    await screen.findByText("TEST未匹配");
    expect(screen.queryByRole("button", { name: "标为已读" })).toBeNull();
  });
  it("rejects a reply for another opportunity", async () => {
    vi.mocked(context.service.followup!.replies).mockImplementation(
      async (id) => (id ? [reply({ opportunityId: "OTHER" })] : []),
    );
    render(<FollowupsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "TEST商机" }));
    await screen.findByText("回复与当前商机不匹配，请刷新核对。");
    expect(screen.queryByText("TEST真实条件回复")).toBeNull();
  });
  it("never offers correction or withdrawal for sample or historical records", async () => {
    mockRecords([
      row({ state: "CORRECTED" }),
      row({ id: "TEST-sample", sample: true }),
    ]);
    render(<FollowupsPage />);
    fireEvent.click(screen.getByRole("tab", { name: "全部" }));
    await selectManual();
    expect(screen.queryByRole("button", { name: "纠正记录" })).toBeNull();
    expect(screen.queryByRole("button", { name: "撤销登记" })).toBeNull();
  });
});
describe("P15 structured and legacy persistence", () => {
  it("does not apply late success to a new user or clear their draft", async () => {
    addRoute();
    let resolve!: (receipt: FollowupReceipt) => void;
    vi.mocked(context.service.followup!.mutate).mockImplementation(
      () =>
        new Promise((r) => {
          resolve = r;
        }),
    );
    const view = render(<FollowupsPage />);
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
    await waitFor(() =>
      expect(context.service.followup!.mutate).toHaveBeenCalledOnce(),
    );
    const binding = vi.mocked(context.service.followup!.mutate).mock.calls[0][0]
      .binding;
    const oldKey = ledger();
    context = { ...context, session: { authenticated: true, userId: "OTHER" } };
    view.rerender(<FollowupsPage />);
    await act(async () =>
      resolve({
        binding,
        status: "SUCCEEDED",
        confirmed: true,
        record: row({
          ...vi.mocked(context.service.followup!.mutate).mock.calls[0][0]
            .values,
          id: "TEST-new",
        }),
      }),
    );
    expect(context.navigate).not.toHaveBeenCalled();
    expect(context.notify).not.toHaveBeenCalled();
    expect(JSON.parse(localStorage.getItem(oldKey)!)).toEqual({});
    expect(stored()).toEqual({});
  });
  it("times out a pending save without discarding the draft or releasing the original operation", async () => {
    addRoute();
    vi.mocked(context.service.followup!.mutate).mockImplementation(
      () => new Promise(() => {}),
    );
    render(<FollowupsPage />);
    await fill();
    vi.useFakeTimers();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
    });
    expect(context.service.followup!.mutate).toHaveBeenCalledOnce();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_001);
    });
    expect(
      screen.getByText("保存结果未确认，请核对原操作，不要重复保存。"),
    ).toBeTruthy();
    expect(Object.values(stored())).toEqual(["PENDING"]);
    expect(
      (screen.getByRole("textbox", { name: "跟进备注" }) as HTMLTextAreaElement)
        .value,
    ).toBe("TEST人工记录");
  });
  it("saves contact time, next action and assigned member with an exact version binding", async () => {
    addRoute();
    vi.mocked(context.service.followup!.mutate).mockImplementation(
      async (input) => ({
        binding: input.binding,
        status: "SUCCEEDED",
        confirmed: true,
        record: row({ ...input.values, id: "TEST-new" }),
      }),
    );
    render(<FollowupsPage />);
    await fill();
    fireEvent.change(screen.getByLabelText("联系时间", { selector: "input" }), {
      target: { value: "2020-01-02T09:00" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: "下一步" }), {
      target: { value: "TEST发送资料" },
    });
    fireEvent.change(screen.getByLabelText("下次跟进", { selector: "input" }), {
      target: { value: "2030-01-02" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
    await waitFor(() =>
      expect(context.navigate).toHaveBeenCalledWith("/followups"),
    );
    const input = vi.mocked(context.service.followup!.mutate).mock.calls[0][0];
    expect(input.binding).toMatchObject({
      opportunityId: "TEST-opp",
      profileVersionId: "TEST-profile-v1",
      action: "create",
    });
    expect(input.values).toMatchObject({
      note: "TEST人工记录",
      nextStep: "TEST发送资料",
      ownerId: "TEST-member",
    });
    expect(input.values!.occurredAt).toMatch(/^2020-01-02T/);
    expect(stored()).toEqual({});
    expect(context.service.addFollowup).not.toHaveBeenCalled();
  });
  it("retains inputs and pending identity after network failure, including clear-drafts and reopening", async () => {
    addRoute();
    vi.mocked(context.service.followup!.mutate).mockRejectedValue(
      new Error("TEST结果未知"),
    );
    const view = render(<FollowupsPage />);
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
    await screen.findByText("TEST结果未知");
    expect(
      (screen.getByRole("textbox", { name: "跟进备注" }) as HTMLTextAreaElement)
        .value,
    ).toBe("TEST人工记录");
    expect(Object.values(stored())).toEqual(["PENDING"]);
    view.unmount();
    act(() => clearLocalDrafts());
    render(<FollowupsPage />);
    expect(
      (screen.getByRole("button", { name: "保存记录" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(context.service.followup!.mutate).toHaveBeenCalledTimes(1);
  });
  it.each(["UNKNOWN", "FAILED", "wrong identity"])(
    "reconciles %s without inventing success",
    async (result) => {
      const binding = {
        opportunityId: "TEST-opp",
        profileVersionId: "TEST-profile-v1",
        action: "create" as const,
        targetId: "",
        targetRevision: 0,
        requestId: "TEST-request",
      };
      localStorage.setItem(
        ledger(),
        JSON.stringify({ [followupKey(binding)]: "PENDING" }),
      );
      vi.mocked(context.service.followup!.operation).mockResolvedValue({
        binding:
          result === "wrong identity"
            ? { ...binding, opportunityId: "OTHER" }
            : binding,
        status: result === "FAILED" ? "FAILED" : "UNKNOWN",
        confirmed: true,
      });
      render(<FollowupsPage />);
      fireEvent.click(screen.getByRole("button", { name: "核对原跟进操作" }));
      await waitFor(() =>
        expect(context.service.followup!.operation).toHaveBeenCalledOnce(),
      );
      await waitFor(() =>
        expect(
          (
            screen.queryByRole("button", {
              name: "核对原跟进操作",
            }) as HTMLButtonElement | null
          )?.disabled || false,
        ).toBe(false),
      );
      expect(Object.keys(stored()).length).toBe(result === "FAILED" ? 0 : 1);
      expect(context.service.followup!.mutate).not.toHaveBeenCalled();
    },
  );
  it("prevents saving a changed opportunity version", async () => {
    addRoute();
    vi.mocked(context.service.opportunities)
      .mockResolvedValueOnce([opportunity])
      .mockResolvedValue([{ ...opportunity, profileVersionId: "new-profile" }]);
    render(<FollowupsPage />);
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
    await screen.findByText(
      "商机或画像版本已变化，请刷新后核对内容，尚未保存。",
    );
    expect(context.service.followup!.mutate).not.toHaveBeenCalled();
    expect(stored()).toEqual({});
  });
  it("protects unsaved input on close and preserves a draft after explicit confirmation", async () => {
    addRoute();
    render(<FollowupsPage />);
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    await screen.findByRole("dialog", { name: "保留未保存内容并关闭？" });
    expect(context.navigate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "保留并关闭" }));
    await waitFor(() =>
      expect(context.navigate).toHaveBeenCalledWith("/followups"),
    );
  });
  it("keeps the real legacy facade and explicitly embeds optional facts without claiming reminders", async () => {
    context.service.followup = undefined;
    addRoute();
    render(<FollowupsPage />);
    await fill();
    fireEvent.change(screen.getByRole("textbox", { name: "下一步" }), {
      target: { value: "TEST下一步" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
    await waitFor(() =>
      expect(context.service.addFollowup).toHaveBeenCalledOnce(),
    );
    expect(vi.mocked(context.service.addFollowup).mock.calls[0][2]).toContain(
      "下一步：TEST下一步",
    );
    expect(vi.mocked(context.service.addFollowup).mock.calls[0][2]).toContain(
      "未设置提醒",
    );
  });
  it("requires correction reason and appends correction instead of erasing the original", async () => {
    vi.mocked(context.service.followup!.mutate).mockImplementation(
      async (input) => ({
        binding: input.binding,
        status: "SUCCEEDED",
        confirmed: true,
        record: row({
          ...input.values,
          id: "TEST-corrected",
          correctsId: input.binding.targetId,
        }),
      }),
    );
    render(<FollowupsPage />);
    await selectManual();
    fireEvent.click(screen.getByRole("button", { name: "纠正记录" }));
    fireEvent.change(screen.getByRole("textbox", { name: "跟进备注" }), {
      target: { value: "TEST修正事实" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
    await screen.findByText("请填写纠正原因，原记录将保留。");
    fireEvent.change(screen.getByRole("textbox", { name: "纠正原因" }), {
      target: { value: "TEST原时间有误" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
    await waitFor(() =>
      expect(context.service.followup!.mutate).toHaveBeenCalledOnce(),
    );
    expect(
      vi.mocked(context.service.followup!.mutate).mock.calls[0][0],
    ).toMatchObject({
      binding: { action: "correct", targetId: "TEST-f1", targetRevision: 1 },
      reason: "TEST原时间有误",
    });
  });
  it("requires a reason and confirmation before withdrawing a manual fact", async () => {
    vi.mocked(context.service.followup!.mutate).mockImplementation(
      async (input) => ({
        binding: input.binding,
        status: "SUCCEEDED",
        confirmed: true,
        record: row({ revision: 2, state: "VOID" }),
      }),
    );
    render(<FollowupsPage />);
    await selectManual();
    fireEvent.click(screen.getByRole("button", { name: "撤销登记" }));
    await screen.findByRole("dialog", { name: "撤销这条人工登记？" });
    expect(context.service.followup!.mutate).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole("textbox", { name: "撤销原因" }), {
      target: { value: "TEST重复登记" },
    });
    fireEvent.click(screen.getByRole("button", { name: "确认撤销" }));
    await waitFor(() =>
      expect(context.service.followup!.mutate).toHaveBeenCalledOnce(),
    );
    expect(
      vi.mocked(context.service.followup!.mutate).mock.calls[0][0].binding
        .action,
    ).toBe("void");
  });
});
