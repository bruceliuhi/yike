// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AppContextValue } from "../../src/renderer/app/context";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import type {
  FollowupReceipt,
  FollowupRecord,
  LinkedReply,
} from "../../src/renderer/domain/followup";
import type { Opportunity } from "../../src/renderer/domain/models";
import { parseRoute } from "../../src/renderer/domain/routes";
import { FollowupsPage } from "../../src/renderer/pages/Followups";
import { PUBLIC_SAMPLE } from "../../src/renderer/pages/Opportunities";
import {
  followupOwner,
  readFollowupOperations,
} from "../../src/renderer/pages/followups/followupOperationStorage";
import {
  ServiceError,
  type YikeService,
} from "../../src/renderer/services/contracts";

let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));

// Isolated authenticated-service fixtures only. No customer service or platform is called.
const opportunity: Opportunity = {
  ...PUBLIC_SAMPLE,
  id: "TEST-reply-only-opportunity",
  title: "TEST只有渠道回复的商机",
  sample: false,
  profileVersionId: "TEST-profile-version",
};
const reply = (changes: Partial<LinkedReply> = {}): LinkedReply => ({
  id: "TEST-matched-reply",
  revision: 1,
  opportunityId: opportunity.id,
  profileVersionId: opportunity.profileVersionId,
  sendRequestId: "TEST-original-send-request",
  platform: "douyin",
  content: "TEST已匹配渠道原文，尚无人工登记",
  receivedAt: "2026-09-10T08:00:00Z",
  read: false,
  sample: false,
  ...changes,
});
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
function target(id = opportunity.id) {
  context.route = parseRoute(
    `#/followups?opportunity=${encodeURIComponent(id)}&tab=replies`,
  );
}
function assertNoRegistration() {
  expect(context.service.addFollowup).not.toHaveBeenCalled();
  expect(context.service.followup?.mutate).not.toHaveBeenCalled();
  expect(context.service.followup?.operation).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "纠正记录" })).toBeNull();
  expect(screen.queryByRole("button", { name: "撤销登记" })).toBeNull();
  expect(context.notify).not.toHaveBeenCalled();
}
beforeEach(() => {
  clearLocalDrafts();
  localStorage.clear();
  sessionStorage.clear();
  context = {
    service: {
      // Empty list is deliberate: the exact authorized detail can exist outside this list.
      opportunities: vi.fn().mockResolvedValue([]),
      opportunity: vi.fn().mockResolvedValue(opportunity),
      followups: vi.fn().mockResolvedValue([]),
      addFollowup: vi.fn(),
      followup: {
        list: vi.fn().mockResolvedValue({ records: [], members: [] }),
        replies: vi
          .fn()
          .mockImplementation(async (id?: string) =>
            id === opportunity.id ? [reply()] : [],
          ),
        mutate: vi.fn(),
        operation: vi.fn(),
      },
    } as unknown as YikeService,
    session: {
      authenticated: true,
      userId: "TEST-reply-user",
      accountScope: { id: "TEST-space-A", version: 1 },
    },
    route: parseRoute("#/followups"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
  };
  target();
});
afterEach(() => {
  cleanup();
  clearLocalDrafts();
  vi.restoreAllMocks();
});

describe("P14 exact matched-reply entry without a manual followup", () => {
  it("authorizes the exact deep-link opportunity and shows its reply without inventing a manual row", async () => {
    render(<FollowupsPage />);
    await screen.findByText(reply().content);
    expect(context.service.opportunity).toHaveBeenCalledWith(opportunity.id);
    expect(context.service.followup!.replies).toHaveBeenCalledWith(
      opportunity.id,
    );
    expect(
      vi
        .mocked(context.service.followup!.replies)
        .mock.calls.every(([id]) => id === opportunity.id),
    ).toBe(true);
    expect(
      screen
        .getByRole("tab", { name: "回复记录" })
        .getAttribute("aria-selected"),
    ).toBe("true");
    expect(
      screen.getByText(`关联发送记录：${reply().sendRequestId}`),
    ).toBeTruthy();
    expect(
      screen.queryByText(
        "未找到目标商机的跟进记录，请核对商机是否已登记或仍可访问。",
      ),
    ).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "人工登记" }));
    expect(screen.queryByText("人工登记已回复")).toBeNull();
    assertNoRegistration();
  });

  it("does not issue any reply query while exact opportunity authorization is unresolved", async () => {
    const gate = deferred<Opportunity>();
    vi.mocked(context.service.opportunity).mockReturnValue(gate.promise);
    render(<FollowupsPage />);
    await waitFor(() =>
      expect(context.service.opportunity).toHaveBeenCalledWith(opportunity.id),
    );
    expect(context.service.followup!.replies).not.toHaveBeenCalled();
    await act(async () => gate.resolve(opportunity));
    await screen.findByText(reply().content);
    assertNoRegistration();
  });

  it.each([
    [404, "NOT_FOUND", "TEST目标商机不存在"],
    [403, "FORBIDDEN", "TEST当前客户空间无权访问该商机"],
  ] as const)(
    "preserves a %i detail failure and never substitutes another or unmatched reply query",
    async (status, code, message) => {
      vi.mocked(context.service.opportunity).mockRejectedValue(
        new ServiceError(code, message, status),
      );
      render(<FollowupsPage />);
      await screen.findByText(message);
      expect(context.service.followup!.replies).not.toHaveBeenCalled();
      expect(screen.queryByText(reply().content)).toBeNull();
      assertNoRegistration();
    },
  );

  it("does not authorize or query a public sample deep link", async () => {
    target("sample");
    await act(async () => {
      render(<FollowupsPage />);
    });
    expect(context.service.opportunity).not.toHaveBeenCalled();
    expect(context.service.followup!.replies).not.toHaveBeenCalled();
    expect(screen.queryByText(reply().content)).toBeNull();
    assertNoRegistration();
  });

  it.each([
    ["sample response", { ...opportunity, sample: true }],
    ["different ID response", { ...opportunity, id: "TEST-other-opportunity" }],
  ] as const)(
    "rejects %s before querying replies",
    async (_reason, returned) => {
      vi.mocked(context.service.opportunity).mockResolvedValue(returned);
      await act(async () => {
        render(<FollowupsPage />);
      });
      expect(context.service.opportunity).toHaveBeenCalledWith(opportunity.id);
      expect(context.service.followup!.replies).not.toHaveBeenCalled();
      expect(screen.queryByText(reply().content)).toBeNull();
      assertNoRegistration();
    },
  );

  it("does not query a customer opportunity or replies for an unauthenticated session", async () => {
    context.session = { authenticated: false };
    await act(async () => {
      render(<FollowupsPage />);
    });
    expect(context.service.opportunity).not.toHaveBeenCalled();
    expect(context.service.followup!.replies).not.toHaveBeenCalled();
    assertNoRegistration();
  });

  it("keeps a matched-reply read failure through an unrelated manual-list refresh", async () => {
    vi.mocked(context.service.followup!.replies).mockImplementation(
      async (id) => {
        if (id === opportunity.id)
          throw new ServiceError(
            "NETWORK",
            "TEST原回复读取失败，结果未知",
            503,
          );
        return [];
      },
    );
    render(<FollowupsPage />);
    await screen.findByText("TEST原回复读取失败，结果未知");
    fireEvent.click(screen.getByRole("button", { name: "刷新" }));
    await waitFor(() =>
      expect(context.service.followup!.list).toHaveBeenCalledTimes(2),
    );
    expect(screen.getByText("TEST原回复读取失败，结果未知")).toBeTruthy();
    expect(screen.queryByText("暂无收到的回复")).toBeNull();
    assertNoRegistration();
  });

  it("rejects an exact-query receipt containing another opportunity instead of displaying it", async () => {
    vi.mocked(context.service.followup!.replies).mockImplementation(
      async (id) =>
        id ? [reply({ opportunityId: "TEST-other-opportunity" })] : [],
    );
    render(<FollowupsPage />);
    await screen.findByText("回复与当前商机不匹配，请刷新核对。");
    expect(context.service.followup!.replies).toHaveBeenCalledWith(
      opportunity.id,
    );
    expect(screen.queryByText(reply().content)).toBeNull();
    assertNoRegistration();
  });

  it("cannot use late authorization from another space to start a reply query", async () => {
    const old = deferred<Opportunity>();
    vi.mocked(context.service.opportunity).mockImplementation(() =>
      context.session.accountScope?.id === "TEST-space-A"
        ? old.promise
        : Promise.reject(
            new ServiceError("FORBIDDEN", "TEST空间B无权访问", 403),
          ),
    );
    const view = render(<FollowupsPage />);
    await waitFor(() =>
      expect(context.service.opportunity).toHaveBeenCalledOnce(),
    );
    context = {
      ...context,
      session: {
        ...context.session,
        accountScope: { id: "TEST-space-B", version: 1 },
      },
    };
    view.rerender(<FollowupsPage />);
    await screen.findByText("TEST空间B无权访问");
    await act(async () => old.resolve(opportunity));
    expect(context.service.followup!.replies).not.toHaveBeenCalled();
    expect(screen.queryByText(reply().content)).toBeNull();
    expect(screen.getByText("TEST空间B无权访问")).toBeTruthy();
    assertNoRegistration();
  });

  it("does not display a late reply from the previous version of the same space", async () => {
    const old = deferred<LinkedReply[]>();
    vi.mocked(context.service.followup!.replies).mockImplementation((id) =>
      id === opportunity.id ? old.promise : Promise.resolve([]),
    );
    const view = render(<FollowupsPage />);
    await waitFor(() =>
      expect(context.service.followup!.replies).toHaveBeenCalledWith(
        opportunity.id,
      ),
    );
    vi.mocked(context.service.opportunity).mockRejectedValue(
      new ServiceError("FORBIDDEN", "TEST空间新版本无权访问", 403),
    );
    context = {
      ...context,
      session: {
        ...context.session,
        accountScope: { id: "TEST-space-A", version: 2 },
      },
    };
    view.rerender(<FollowupsPage />);
    await screen.findByText("TEST空间新版本无权访问");
    await act(async () => old.resolve([reply()]));
    expect(screen.queryByText(reply().content)).toBeNull();
    expect(screen.getByText("TEST空间新版本无权访问")).toBeTruthy();
    assertNoRegistration();
  });

  it("switches an exact deep link without allowing the previous target's late reply to overwrite it", async () => {
    const old = deferred<LinkedReply[]>();
    const next = { ...opportunity, id: "TEST-next-opportunity" };
    vi.mocked(context.service.opportunity).mockImplementation(async (id) =>
      id === next.id ? next : opportunity,
    );
    vi.mocked(context.service.followup!.replies).mockImplementation((id) =>
      id === opportunity.id
        ? old.promise
        : Promise.resolve(
            id === next.id
              ? [
                  reply({
                    id: "TEST-next-reply",
                    opportunityId: next.id,
                    content: "TEST新目标回复",
                  }),
                ]
              : [],
          ),
    );
    const view = render(<FollowupsPage />);
    await waitFor(() =>
      expect(context.service.followup!.replies).toHaveBeenCalledWith(
        opportunity.id,
      ),
    );
    context = {
      ...context,
      route: parseRoute(`#/followups?opportunity=${next.id}&tab=replies`),
    };
    view.rerender(<FollowupsPage />);
    await screen.findByText("TEST新目标回复");
    await act(async () => old.resolve([reply()]));
    expect(screen.queryByText(reply().content)).toBeNull();
    expect(screen.getByText("TEST新目标回复")).toBeTruthy();
    expect(context.service.opportunity).toHaveBeenLastCalledWith(next.id);
    assertNoRegistration();
  });
});

describe("P14 selection changes during asynchronous work", () => {
  const manual: FollowupRecord = {
    id: "TEST-manual-before-withdrawal",
    opportunityId: opportunity.id,
    profileVersionId: opportunity.profileVersionId,
    revision: 1,
    title: opportunity.title,
    status: "CONTACTED",
    note: "TEST待核对人工事实",
    createdAt: "2026-09-10T07:00:00Z",
    occurredAt: null,
    nextStep: "",
    nextFollowupAt: null,
    ownerId: "TEST-reply-user",
    ownerName: "TEST成员",
    state: "ACTIVE",
    kind: "manual",
    sample: false,
    replyCount: 1,
  };
  it.each(["mark-read", "void"] as const)(
    "does not dispatch an old %s preflight after selecting a different target",
    async (action) => {
      vi.mocked(context.service.followup!.list).mockResolvedValue({
        records: [manual],
        members: [],
      });
      const view = render(<FollowupsPage />);
      await screen.findByText(reply().content);
      if (action === "void") {
        fireEvent.click(screen.getByRole("tab", { name: "人工登记" }));
        fireEvent.click(
          await screen.findByRole("button", { name: "撤销登记" }),
        );
        fireEvent.change(screen.getByRole("textbox", { name: "撤销原因" }), {
          target: { value: "TEST需核对事实" },
        });
      }
      const old = deferred<Opportunity>();
      vi.mocked(context.service.opportunity).mockReturnValueOnce(old.promise);
      fireEvent.click(
        screen.getByRole("button", {
          name: action === "void" ? "确认撤销" : "标为已读",
        }),
      );
      await waitFor(() =>
        expect(context.service.opportunity).toHaveBeenCalledTimes(2),
      );
      const next = { ...opportunity, id: "TEST-different-target" };
      vi.mocked(context.service.opportunity).mockResolvedValue(next);
      context = {
        ...context,
        route: parseRoute(`#/followups?opportunity=${next.id}&tab=replies`),
      };
      view.rerender(<FollowupsPage />);
      await waitFor(() =>
        expect(context.service.opportunity).toHaveBeenLastCalledWith(next.id),
      );
      await act(async () => old.resolve(opportunity));
      expect(
        screen.queryByRole("dialog", { name: "撤销这条人工登记？" }),
      ).toBeNull();
      expect(context.service.followup!.mutate).not.toHaveBeenCalled();
      expect(
        readFollowupOperations(followupOwner(context.session)).pending,
      ).toBeNull();
      expect(context.notify).not.toHaveBeenCalled();
    },
  );

  it("retains the original mark-read request when a dispatched result arrives after leaving its target", async () => {
    const result = deferred<FollowupReceipt>();
    vi.mocked(context.service.followup!.mutate).mockReturnValue(result.promise);
    const view = render(<FollowupsPage />);
    await screen.findByText(reply().content);
    fireEvent.click(screen.getByRole("button", { name: "标为已读" }));
    await waitFor(() =>
      expect(context.service.followup!.mutate).toHaveBeenCalledOnce(),
    );
    const original = vi.mocked(context.service.followup!.mutate).mock
      .calls[0][0].binding;
    const next = { ...opportunity, id: "TEST-different-target" };
    vi.mocked(context.service.opportunity).mockResolvedValue(next);
    context = {
      ...context,
      route: parseRoute(`#/followups?opportunity=${next.id}&tab=replies`),
    };
    view.rerender(<FollowupsPage />);
    await waitFor(() =>
      expect(context.service.opportunity).toHaveBeenLastCalledWith(next.id),
    );
    await act(async () =>
      result.resolve({
        binding: original,
        status: "SUCCEEDED",
        confirmed: true,
        reply: reply({ revision: 2, read: true }),
      }),
    );
    expect(
      readFollowupOperations(followupOwner(context.session)).pending,
    ).toEqual(original);
    expect(context.service.followup!.mutate).toHaveBeenCalledOnce();
    expect(context.service.followup!.operation).not.toHaveBeenCalled();
    expect(context.notify).not.toHaveBeenCalled();
  });

  it("does not reset an explicitly selected date when the initial manual-list request finishes late", async () => {
    const list = deferred<{
      records: FollowupRecord[];
      members: { id: string; name: string }[];
    }>();
    vi.mocked(context.service.followup!.list).mockReturnValue(list.promise);
    render(<FollowupsPage />);
    await screen.findByText(reply().content);
    fireEvent.change(screen.getByLabelText("筛选记录日期"), {
      target: { value: "2026-09-01" },
    });
    fireEvent.click(screen.getByRole("tab", { name: "全部" }));
    await act(async () => list.resolve({ records: [manual], members: [] }));
    expect(
      (screen.getByLabelText("筛选记录日期") as HTMLInputElement).value,
    ).toBe("2026-09-01");
    expect(
      screen.getByRole("tab", { name: "全部" }).getAttribute("aria-selected"),
    ).toBe("true");
    expect(
      (
        screen.getByRole("combobox", {
          name: "查看商机回复",
        }) as HTMLSelectElement
      ).value,
    ).toBe(opportunity.id);
    expect(screen.getByText(reply().content)).toBeTruthy();
    expect(screen.queryByRole("button", { name: manual.title })).toBeNull();
    expect(screen.queryByText("已定位目标商机的最新登记。")).toBeNull();
  });

  it("does not focus the original deep-link row after the reply selector changes during list loading", async () => {
    const list = deferred<{
      records: FollowupRecord[];
      members: { id: string; name: string }[];
    }>();
    const next = {
      ...opportunity,
      id: "TEST-selected-reply-target",
      title: "TEST用户选择的商机",
    };
    vi.mocked(context.service.followup!.list).mockReturnValue(list.promise);
    vi.mocked(context.service.opportunities).mockResolvedValue([
      opportunity,
      next,
    ]);
    vi.mocked(context.service.opportunity).mockImplementation(async (id) =>
      id === next.id ? next : opportunity,
    );
    vi.mocked(context.service.followup!.replies).mockImplementation(
      async (id) =>
        id === next.id
          ? [
              reply({
                id: "TEST-selected-reply",
                opportunityId: next.id,
                content: "TEST用户选择的回复",
              }),
            ]
          : [reply()],
    );
    render(<FollowupsPage />);
    await screen.findByText(reply().content);
    fireEvent.change(screen.getByRole("combobox", { name: "查看商机回复" }), {
      target: { value: next.id },
    });
    await screen.findByText("TEST用户选择的回复");
    await act(async () => list.resolve({ records: [manual], members: [] }));
    expect(
      screen.getByRole("button", { name: manual.title }).closest("tr")
        ?.className,
    ).not.toBe("selected");
    expect(screen.queryByText("已定位目标商机的最新登记。")).toBeNull();
    expect(
      (
        screen.getByRole("combobox", {
          name: "查看商机回复",
        }) as HTMLSelectElement
      ).value,
    ).toBe(next.id);
    fireEvent.click(screen.getByRole("tab", { name: "人工登记" }));
    expect(screen.queryByText(manual.note)).toBeNull();
    assertNoRegistration();
  });
});
