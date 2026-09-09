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
import { FollowupsPage } from "../../src/renderer/pages/Followups";
import { PUBLIC_SAMPLE } from "../../src/renderer/pages/Opportunities";
import { parseRoute } from "../../src/renderer/domain/routes";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { operationLedgerKey } from "../../src/renderer/app/operationLedger";
import {
  followupKey,
  type FollowupReceipt,
  type FollowupRecord,
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
  profileVersionId: "TEST-profile",
  updatedAt: "2026-09-09T09:00:00Z",
};
const row: FollowupRecord = {
  id: "TEST-f1",
  opportunityId: opportunity.id,
  profileVersionId: opportunity.profileVersionId,
  revision: 1,
  title: "TEST空间A记录",
  status: "CONTACTED",
  note: "TEST旧空间事实",
  createdAt: "2026-09-09T09:00:00Z",
  occurredAt: null,
  nextStep: "",
  nextFollowupAt: "2030-01-01T09:00:00Z",
  ownerId: "TEST-user",
  ownerName: "TEST成员",
  state: "ACTIVE",
  kind: "manual",
  sample: false,
};
const snapshot = {
  records: [row],
  members: [{ id: "TEST-user", name: "TEST成员" }],
};
function changeScope(id: string, version = 1) {
  context = {
    ...context,
    session: { ...context.session, accountScope: { id, version } },
  };
}
async function fill() {
  await screen.findByRole("option", { name: "TEST商机" });
  fireEvent.change(screen.getByRole("combobox", { name: "关联商机" }), {
    target: { value: opportunity.id },
  });
  fireEvent.click(screen.getByRole("radio", { name: "已联系" }));
  fireEvent.change(screen.getByRole("textbox", { name: "跟进备注" }), {
    target: { value: "TEST空间A未保存正文" },
  });
}
beforeEach(() => {
  clearLocalDrafts();
  localStorage.clear();
  sessionStorage.clear();
  context = {
    service: {
      opportunities: vi.fn().mockResolvedValue([opportunity]),
      followups: vi.fn().mockResolvedValue([]),
      addFollowup: vi.fn(),
      followup: {
        list: vi.fn().mockResolvedValue(snapshot),
        replies: vi.fn().mockResolvedValue([]),
        mutate: vi.fn(),
        operation: vi.fn(),
      },
    } as unknown as YikeService,
    session: {
      authenticated: true,
      userId: "TEST-user",
      accountScope: { id: "TEST-space-A", version: 1 },
    },
    route: parseRoute("#/followups?add=1"),
    notify: vi.fn(),
    navigate: vi.fn(),
    refreshSession: vi.fn(),
  };
});
afterEach(() => {
  vi.restoreAllMocks();
  cleanup();
  clearLocalDrafts();
  vi.useRealTimers();
});
it.each([
  ["TEST-space-B", 1],
  ["TEST-space-A", 2],
])(
  "isolates rows and form immediately for same user in %s v%i",
  async (id, version) => {
    const view = render(<FollowupsPage />);
    await fill();
    expect(screen.getByRole("button", { name: "TEST空间A记录" })).toBeTruthy();
    vi.mocked(context.service.followup!.list).mockImplementation(
      () => new Promise(() => {}),
    );
    changeScope(id as string, version as number);
    view.rerender(<FollowupsPage />);
    expect(screen.queryByDisplayValue("TEST空间A未保存正文")).toBeNull();
    expect(screen.queryByRole("button", { name: "TEST空间A记录" })).toBeNull();
    await waitFor(() =>
      expect(context.service.followup!.list).toHaveBeenCalledTimes(2),
    );
    changeScope("TEST-space-A");
    view.rerender(<FollowupsPage />);
    expect(screen.getByDisplayValue("TEST空间A未保存正文")).toBeTruthy();
  },
);
it("drops old-space preflight before dispatching a write", async () => {
  const view = render(<FollowupsPage />);
  await fill();
  let release!: (value: (typeof opportunity)[]) => void;
  vi.mocked(context.service.opportunities).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        release = resolve;
      }),
  );
  fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
  await waitFor(() => expect(release).toBeTypeOf("function"));
  changeScope("TEST-space-B");
  view.rerender(<FollowupsPage />);
  await act(async () => release([opportunity]));
  expect(context.service.followup!.mutate).not.toHaveBeenCalled();
});
it("retains an old-space uncertain write until returning to its exact scope", async () => {
  let release!: (value: FollowupReceipt) => void;
  vi.mocked(context.service.followup!.mutate).mockImplementation(
    () =>
      new Promise((resolve) => {
        release = resolve;
      }),
  );
  const view = render(<FollowupsPage />);
  await fill();
  fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
  await waitFor(() =>
    expect(context.service.followup!.mutate).toHaveBeenCalledOnce(),
  );
  const input = vi.mocked(context.service.followup!.mutate).mock.calls[0][0];
  changeScope("TEST-space-B");
  view.rerender(<FollowupsPage />);
  expect(screen.queryByRole("button", { name: "核对原跟进操作" })).toBeNull();
  await act(async () =>
    release({
      binding: input.binding,
      status: "SUCCEEDED",
      confirmed: true,
      record: { ...row, ...input.values!, id: "TEST-created" },
    }),
  );
  expect(context.notify).not.toHaveBeenCalled();
  expect(context.navigate).not.toHaveBeenCalled();
  changeScope("TEST-space-A");
  context.route = parseRoute("#/followups");
  view.rerender(<FollowupsPage />);
  expect(screen.getByRole("button", { name: "核对原跟进操作" })).toBeTruthy();
  expect(context.service.followup!.operation).not.toHaveBeenCalled();
  vi.mocked(context.service.followup!.operation).mockResolvedValue({
    binding: input.binding,
    status: "FAILED",
    confirmed: true,
  });
  fireEvent.click(screen.getByRole("button", { name: "核对原跟进操作" }));
  await waitFor(() =>
    expect(context.service.followup!.operation).toHaveBeenCalledWith(
      input.binding,
    ),
  );
});
it("keeps unbound legacy request IDs visible and cannot query or replace them in the current space", async () => {
  const binding = {
    opportunityId: opportunity.id,
    profileVersionId: opportunity.profileVersionId,
    action: "create" as const,
    targetId: "",
    targetRevision: 0,
    requestId: "TEST-legacy-unbound-request",
  };
  const key = operationLedgerKey("followup-operations", "TEST-user");
  localStorage.setItem(
    key,
    JSON.stringify({ [followupKey(binding)]: "PENDING" }),
  );
  render(<FollowupsPage />);
  await fill();
  expect(screen.getByDisplayValue(binding.requestId)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "核对原跟进操作" })).toBeNull();
  expect(
    (screen.getByRole("button", { name: "保存记录" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  expect(context.service.followup!.operation).not.toHaveBeenCalled();
  expect(JSON.parse(localStorage.getItem(key)!)).toEqual({
    [followupKey(binding)]: "PENDING",
  });
});
it.each(["SUCCEEDED", "FAILED", "edited"] as const)(
  "handles the resolved original draft: %s",
  async (outcome) => {
    vi.mocked(context.service.followup!.mutate).mockRejectedValue(
      new Error("TEST保存结果未知"),
    );
    const view = render(<FollowupsPage />);
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
    await screen.findByText("TEST保存结果未知");
    const input = vi.mocked(context.service.followup!.mutate).mock.calls[0][0];
    if (outcome === "edited")
      fireEvent.change(screen.getByRole("textbox", { name: "跟进备注" }), {
        target: { value: "TEST后续人工修改" },
      });
    // The user keeps and closes the uncertain form before reconciling its original request.
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    fireEvent.click(await screen.findByRole("button", { name: "保留并关闭" }));
    context.route = parseRoute("#/followups");
    view.rerender(<FollowupsPage />);
    vi.mocked(context.service.followup!.operation).mockResolvedValue({
      binding: input.binding,
      status: outcome === "FAILED" ? "FAILED" : "SUCCEEDED",
      confirmed: true,
      ...(outcome === "FAILED"
        ? {}
        : { record: { ...row, ...input.values!, id: "TEST-created" } }),
    });
    fireEvent.click(screen.getByRole("button", { name: "核对原跟进操作" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "核对原跟进操作" }),
      ).toBeNull(),
    );
    context.route = parseRoute("#/followups?add=1");
    view.rerender(<FollowupsPage />);
    if (outcome === "SUCCEEDED") {
      vi.mocked(context.service.followup!.mutate).mockImplementation(
        async (next) => ({
          binding: next.binding,
          status: "SUCCEEDED",
          confirmed: true,
          record: { ...row, ...next.values!, id: "TEST-duplicate" },
        }),
      );
      const oldBody = screen.queryByDisplayValue("TEST空间A未保存正文");
      if (oldBody)
        fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
      await waitFor(() =>
        expect(screen.queryByDisplayValue("TEST空间A未保存正文")).toBeNull(),
      );
      expect(context.service.followup!.mutate).toHaveBeenCalledOnce();
    } else
      expect(
        screen.getByDisplayValue(
          outcome === "edited" ? "TEST后续人工修改" : "TEST空间A未保存正文",
        ),
      ).toBeTruthy();
  },
);
it("preserves a never-opened legacy session lock when Settings clears drafts first", async () => {
  const binding = {
    opportunityId: opportunity.id,
    profileVersionId: opportunity.profileVersionId,
    action: "create" as const,
    targetId: "",
    targetRevision: 0,
    requestId: "TEST-not-read-before-clear",
  };
  sessionStorage.setItem(
    "yike.ui.draft.v1.followup-operations.TEST-user",
    JSON.stringify({ [followupKey(binding)]: "PENDING" }),
  );
  clearLocalDrafts();
  render(<FollowupsPage />);
  await fill();
  expect(screen.getByDisplayValue(binding.requestId)).toBeTruthy();
  expect(
    (screen.getByRole("button", { name: "保存记录" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  expect(context.service.followup!.mutate).not.toHaveBeenCalled();
});
it.each(["throw", "silent"])(
  "keeps the original durable lock when acknowledgement storage fails: %s",
  async (failure) => {
    vi.mocked(context.service.followup!.mutate).mockRejectedValue(
      new Error("TEST保存结果未知"),
    );
    const view = render(<FollowupsPage />);
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
    await screen.findByText("TEST保存结果未知");
    const input = vi.mocked(context.service.followup!.mutate).mock.calls[0][0];
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    fireEvent.click(await screen.findByRole("button", { name: "保留并关闭" }));
    context.route = parseRoute("#/followups");
    view.rerender(<FollowupsPage />);
    vi.mocked(context.service.followup!.operation).mockResolvedValue({
      binding: input.binding,
      status: "SUCCEEDED",
      confirmed: true,
      record: { ...row, ...input.values!, id: "TEST-created" },
    });
    const original = Storage.prototype.setItem;
    const fault = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(function (this: Storage, key: string, value: string) {
        if (this === sessionStorage && key.includes("followup-resolved:")) {
          if (failure === "throw") throw new Error("TEST session quota");
          return;
        }
        return original.call(this, key, value);
      });
    fireEvent.click(screen.getByRole("button", { name: "核对原跟进操作" }));
    await waitFor(() =>
      expect(context.service.followup!.operation).toHaveBeenCalledOnce(),
    );
    await waitFor(() =>
      expect(
        screen
          .getByRole("button", { name: "核对原跟进操作" })
          .getAttribute("disabled"),
      ).toBeNull(),
    );
    expect(screen.getByRole("button", { name: "核对原跟进操作" })).toBeTruthy();
    fault.mockRestore();
    context.route = parseRoute("#/followups?add=1");
    view.rerender(<FollowupsPage />);
    expect(screen.getByDisplayValue("TEST空间A未保存正文")).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "保存记录" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  },
);
it("keeps the verified acknowledgement when removing the old submitted draft fails", async () => {
  vi.mocked(context.service.followup!.mutate).mockRejectedValue(
    new Error("TEST保存结果未知"),
  );
  const view = render(<FollowupsPage />);
  await fill();
  fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
  await screen.findByText("TEST保存结果未知");
  const input = vi.mocked(context.service.followup!.mutate).mock.calls[0][0];
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  fireEvent.click(await screen.findByRole("button", { name: "保留并关闭" }));
  context.route = parseRoute("#/followups");
  view.rerender(<FollowupsPage />);
  vi.mocked(context.service.followup!.operation).mockResolvedValue({
    binding: input.binding,
    status: "SUCCEEDED",
    confirmed: true,
    record: { ...row, ...input.values!, id: "TEST-created" },
  });
  fireEvent.click(screen.getByRole("button", { name: "核对原跟进操作" }));
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: "核对原跟进操作" })).toBeNull(),
  );
  const keys = Array.from({ length: sessionStorage.length }, (_, i) =>
    sessionStorage.key(i)!,
  );
  const draftKey = keys.find((key) => key.includes("followup:v3:"))!;
  const ackKey = keys.find((key) => key.includes("followup-resolved:"))!;
  const oldAcknowledgement = sessionStorage.getItem(ackKey);
  const original = Storage.prototype.removeItem;
  const fault = vi
    .spyOn(Storage.prototype, "removeItem")
    .mockImplementation(function (this: Storage, key: string) {
      if (this === sessionStorage && key === draftKey)
        throw new Error("TEST removal unavailable");
      return original.call(this, key);
    });
  context.route = parseRoute("#/followups?add=1");
  view.rerender(<FollowupsPage />);
  await waitFor(() =>
    expect(screen.queryByDisplayValue("TEST空间A未保存正文")).toBeNull(),
  );
  expect(sessionStorage.getItem(draftKey)).toContain("TEST空间A未保存正文");
  expect(sessionStorage.getItem(ackKey)).toBe(oldAcknowledgement);
  expect(context.service.followup!.mutate).toHaveBeenCalledOnce();
  fault.mockRestore();
});

it("retains a verified legacy acknowledgement when submitted draft deletion fails", async () => {
  context.service.followup = undefined;
  vi.mocked(context.service.addFollowup).mockResolvedValue(undefined);
  render(<FollowupsPage />);
  await fill();
  const draftKey = Array.from({ length: sessionStorage.length }, (_, i) =>
    sessionStorage.key(i)!,
  ).find((key) => key.includes("followup:v3:"))!;
  const original = Storage.prototype.removeItem;
  const fault = vi
    .spyOn(Storage.prototype, "removeItem")
    .mockImplementation(function (this: Storage, key: string) {
      if (this === sessionStorage && key === draftKey)
        throw new Error("TEST legacy draft removal unavailable");
      return original.call(this, key);
    });
  fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
  await waitFor(() =>
    expect(context.notify).toHaveBeenCalledWith("跟进事实已保存。", "success"),
  );
  expect(context.service.addFollowup).toHaveBeenCalledOnce();
  expect(sessionStorage.getItem(draftKey)).toContain("TEST空间A未保存正文");
  const ackKey = Array.from({ length: sessionStorage.length }, (_, i) =>
    sessionStorage.key(i)!,
  ).find((key) => key.includes("followup-resolved:"));
  expect(
    ackKey,
    "A successful legacy write must retain its draft hash before dropping the durable lock",
  ).toBeDefined();
  const value = JSON.parse(sessionStorage.getItem(ackKey!) || "{}");
  expect(Object.keys(value).length).toBeGreaterThan(0);
  fault.mockRestore();
});
it.each(["throw", "silent"])(
  "retains the original legacy lock when the success ACK cannot be stored: %s",
  async (failure) => {
    context.service.followup = undefined;
    vi.mocked(context.service.addFollowup).mockResolvedValue(undefined);
    render(<FollowupsPage />);
    await fill();
    const original = Storage.prototype.setItem;
    const fault = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(function (this: Storage, key: string, value: string) {
        if (this === sessionStorage && key.includes("followup-resolved:")) {
          if (failure === "throw")
            throw new Error("TEST acknowledgement unavailable");
          return;
        }
        return original.call(this, key, value);
      });
    fireEvent.click(screen.getByRole("button", { name: "保存记录" }));
    await waitFor(() =>
      expect(context.service.addFollowup).toHaveBeenCalledOnce(),
    );
    await screen.findByText(
      /本次人工登记接口已返回成功，但本机确认记录无法可靠更新/,
    );
    expect(screen.getByDisplayValue("TEST空间A未保存正文")).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "保存记录" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(context.notify).not.toHaveBeenCalledWith(
      "跟进事实已保存。",
      "success",
    );
    expect(
      Array.from({ length: localStorage.length }, (_, i) =>
        localStorage.key(i)!,
      ).some((key) => key.startsWith("yike.ui.followup-operation.v2.")),
    ).toBe(true);
    fault.mockRestore();
  },
);
