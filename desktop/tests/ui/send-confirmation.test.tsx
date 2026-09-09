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
import {
  SendConfirmation,
  contactFingerprint,
} from "../../src/renderer/pages/Outreach";
import { PUBLIC_SAMPLE } from "../../src/renderer/pages/Opportunities";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { operationLedgerKey } from "../../src/renderer/app/operationLedger";
import { parseRoute } from "../../src/renderer/domain/routes";
import type { AppContextValue } from "../../src/renderer/app/context";
import type {
  ContactDraft,
  ContactVerification,
  Opportunity,
  PlatformConnection,
} from "../../src/renderer/domain/models";
import {
  ServiceError,
  type YikeService,
} from "../../src/renderer/services/contracts";

let context: AppContextValue;
let row: Opportunity;
let draft: ContactDraft;
let connection: PlatformConnection;
let onClose: ReturnType<typeof vi.fn<() => void>>;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
function proof(
  fingerprint = contactFingerprint(draft, row, connection),
  change: Partial<ContactVerification> = {},
): ContactVerification {
  return {
    allowed: true,
    fingerprint,
    confirmationToken: "isolated-confirmation-token",
    expiresAt: new Date(Date.now() + 60_000).toISOString(),
    opportunityId: row.id,
    accountId: draft.accountId,
    channel: draft.channel,
    recipientId: "isolated-recipient-id",
    recipientLabel: "已映射的隔离测试对象",
    ...change,
  };
}
function mount() {
  return render(
    <SendConfirmation
      row={row}
      draft={draft}
      connection={connection}
      onClose={onClose}
    />,
  );
}
function sendButton() {
  return screen.getByRole("button", {
    name: "确认并发送",
  }) as HTMLButtonElement;
}
function checkbox() {
  return screen.getByRole("checkbox", {
    name: "我已核对联系对象、发送账号和内容",
  });
}
async function verifyAndCheck() {
  fireEvent.click(screen.getByRole("button", { name: "核验发送条件" }));
  await screen.findByText("已映射的隔离测试对象");
  fireEvent.click(checkbox());
}
function storedAttempts() {
  return JSON.parse(
    localStorage.getItem(
      operationLedgerKey("send-attempts", context.session.userId!),
    ) || "{}",
  ) as Record<string, string>;
}
function attemptKey() {
  return JSON.stringify([row.id, draft.channel]);
}
function sentKey() {
  return JSON.stringify([row.id, draft.channel, draft.version]);
}
beforeEach(() => {
  clearLocalDrafts();
  sessionStorage.clear();
  localStorage.clear();
  onClose = vi.fn();
  row = {
    ...PUBLIC_SAMPLE,
    id: "isolated-opportunity-id",
    title: "隔离测试商机",
    sample: false,
    profileVersionId: "isolated-profile-version",
    profileStatus: "CONFIRMED",
    sourceStatus: "OPEN",
  };
  draft = {
    opportunityId: row.id,
    channel: "comment",
    version: 2,
    content: "仅用于隔离测试的完整草稿。",
    savedContent: "仅用于隔离测试的完整草稿。",
    accountId: "isolated-account",
    recipient: "待映射对象",
  };
  connection = {
    platform: "xhs",
    status: "CONNECTED",
    accountId: draft.accountId,
    accountName: "隔离测试账号",
    capabilities: ["comment"],
  };
  context = {
    service: {
      verifyContact: vi.fn((_draft: ContactDraft, fingerprint: string) =>
        Promise.resolve(proof(fingerprint)),
      ),
      send: vi.fn().mockResolvedValue({ status: "SENT" }),
    } as unknown as YikeService,
    session: { authenticated: true, userId: crypto.randomUUID() },
    sessionReady: true,
    route: parseRoute("#/outreach?confirm=send"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
  };
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("send confirmation with isolated available service fixtures", () => {
  it("enables only after mapped proof and explicit review, rechecks on send, and records the actual outcome", async () => {
    mount();
    fireEvent.click(checkbox());
    expect(sendButton().disabled).toBe(true);
    await verifyAndCheck();
    expect(sendButton().disabled).toBe(false);
    expect(context.service.verifyContact).toHaveBeenCalledWith(
      draft,
      contactFingerprint(draft, row, connection),
    );
    fireEvent.click(sendButton());
    await waitFor(() => expect(context.service.send).toHaveBeenCalledOnce());
    expect(context.service.verifyContact).toHaveBeenCalledTimes(2);
    expect(context.service.send).toHaveBeenCalledWith(
      draft,
      "isolated-confirmation-token",
    );
    await screen.findByText("此版本内容已发送，不能重复发送。");
    expect(storedAttempts()[sentKey()]).toBe("SENT");
    expect(sendButton().disabled).toBe(true);
    expect(context.notify).toHaveBeenCalledWith(
      "渠道已确认发送成功。",
      "success",
    );
  });

  it.each([
    ["denied", { allowed: false }],
    ["wrong fingerprint", { fingerprint: "another-fingerprint" }],
    ["wrong opportunity", { opportunityId: "another-opportunity" }],
    ["wrong account", { accountId: "another-account" }],
    ["wrong channel", { channel: "dm" }],
    ["no mapped recipient", { recipientId: "" }],
    ["no readable recipient", { recipientLabel: "" }],
    ["no token", { confirmationToken: "" }],
    ["expired", { expiresAt: "2000-01-01T00:00:00Z" }],
  ] as [string, Partial<ContactVerification>][])(
    "rejects %s proof before enabling send",
    async (_name, change) => {
      context.service.verifyContact = vi
        .fn()
        .mockResolvedValue(proof(undefined, change));
      mount();
      fireEvent.click(screen.getByRole("button", { name: "核验发送条件" }));
      await screen.findByText("对象、账号或草稿核验未通过，请重新核对。");
      fireEvent.click(checkbox());
      expect(sendButton().disabled).toBe(true);
      expect(context.service.send).not.toHaveBeenCalled();
    },
  );

  it("expires a previously valid proof and clears the confirmation checkbox", async () => {
    context.service.verifyContact = vi
      .fn()
      .mockImplementation(() =>
        Promise.resolve(
          proof(undefined, {
            expiresAt: new Date(Date.now() + 80).toISOString(),
          }),
        ),
      );
    mount();
    await verifyAndCheck();
    expect(sendButton().disabled).toBe(false);
    await screen.findByText("核验结果已过期，请重新核验。");
    expect(sendButton().disabled).toBe(true);
    expect((checkbox() as HTMLInputElement).checked).toBe(false);
    expect(context.service.send).not.toHaveBeenCalled();
  });

  it("rejects a changed mapped recipient in the final preflight and requires another review", async () => {
    vi.mocked(context.service.verifyContact)
      .mockResolvedValueOnce(proof())
      .mockResolvedValueOnce(
        proof(undefined, {
          recipientId: "changed-recipient",
          recipientLabel: "不同测试对象",
        }),
      );
    mount();
    await verifyAndCheck();
    fireEvent.click(sendButton());
    await screen.findByText("发送对象或条件已变化，请重新核验并确认。");
    expect(context.service.send).not.toHaveBeenCalled();
    expect(sendButton().disabled).toBe(true);
    expect((checkbox() as HTMLInputElement).checked).toBe(false);
    expect(storedAttempts()).toEqual({});
  });
  it("rejects an expired proof returned by the final preflight", async () => {
    vi.mocked(context.service.verifyContact)
      .mockResolvedValueOnce(proof())
      .mockResolvedValueOnce(
        proof(undefined, { expiresAt: "2000-01-01T00:00:00Z" }),
      );
    mount();
    await verifyAndCheck();
    fireEvent.click(sendButton());
    await screen.findByText("发送对象或条件已变化，请重新核验并确认。");
    expect(context.service.send).not.toHaveBeenCalled();
    expect(storedAttempts()).toEqual({});
  });

  it.each(["content", "account", "source"] as const)(
    "blocks %s changes after proof without losing the original preview",
    async (change) => {
      const original = draft.content;
      const view = mount();
      await verifyAndCheck();
      if (change === "content")
        draft = {
          ...draft,
          content: "修改后的草稿",
          savedContent: "修改后的草稿",
          version: 3,
        };
      if (change === "account")
        connection = { ...connection, status: "EXPIRED" };
      if (change === "source") row = { ...row, sourceStatus: "CLOSED" };
      view.rerender(
        <SendConfirmation
          row={row}
          draft={draft}
          connection={connection}
          onClose={onClose}
        />,
      );
      expect(
        screen.getByText("内容或连接已变化，请返回重新确认。"),
      ).toBeTruthy();
      expect(screen.getByText(original)).toBeTruthy();
      expect(sendButton().disabled).toBe(true);
      expect(context.service.send).not.toHaveBeenCalled();
    },
  );

  it("never verifies or sends a public sample even with complete fields and a checked review", () => {
    row = { ...row, sample: true };
    mount();
    fireEvent.click(checkbox());
    expect(screen.getByText("公开样例未入客户库，当前不可发送。")).toBeTruthy();
    expect(sendButton().disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "核验发送条件" })).toBeNull();
    expect(context.service.verifyContact).not.toHaveBeenCalled();
    expect(context.service.send).not.toHaveBeenCalled();
  });
  it.each([
    ["expired connection", { status: "EXPIRED" }],
    ["disconnected account", { status: "DISCONNECTED" }],
    ["another account", { accountId: "different-account" }],
    ["missing capability", { capabilities: ["read"] }],
    ["another channel capability", { capabilities: ["send_dm"] }],
  ] as [string, Partial<PlatformConnection>][])(
    "blocks %s at the confirmation boundary",
    (_name, change) => {
      connection = { ...connection, ...change };
      mount();
      fireEvent.click(checkbox());
      expect(screen.getByText("请先连接并选择有效发送账号。")).toBeTruthy();
      expect(sendButton().disabled).toBe(true);
      expect(screen.queryByRole("button", { name: "核验发送条件" })).toBeNull();
      expect(context.service.verifyContact).not.toHaveBeenCalled();
      expect(context.service.send).not.toHaveBeenCalled();
    },
  );
  it("rejects a draft belonging to another opportunity before requesting verification", () => {
    draft = { ...draft, opportunityId: "another-opportunity" };
    mount();
    fireEvent.click(checkbox());
    expect(
      screen.getByText("草稿与当前商机不匹配，请返回重新选择。"),
    ).toBeTruthy();
    expect(sendButton().disabled).toBe(true);
    expect(context.service.verifyContact).not.toHaveBeenCalled();
    expect(context.service.send).not.toHaveBeenCalled();
  });

  it("persists PENDING before the send call and ignores repeated clicks while awaiting a result", async () => {
    let resolve!: (value: { status: string }) => void;
    context.service.send = vi.fn(() => {
      expect(storedAttempts()[attemptKey()]).toBe("PENDING");
      return new Promise<{ status: string }>((done) => {
        resolve = done;
      });
    });
    mount();
    await verifyAndCheck();
    const button = sendButton();
    fireEvent.click(button);
    fireEvent.click(button);
    await waitFor(() => expect(context.service.send).toHaveBeenCalledOnce());
    fireEvent.click(button);
    expect(context.service.send).toHaveBeenCalledOnce();
    expect(context.notify).not.toHaveBeenCalled();
    await act(async () => resolve({ status: "PENDING" }));
    await screen.findByText(
      "此版本发送结果尚待确认，请核对平台记录，避免重复发送。",
    );
    expect(sendButton().disabled).toBe(true);
    expect(context.notify).toHaveBeenCalledWith(
      "发送请求已提交，结果尚待渠道确认。",
      "info",
    );
  });

  it("does not send after leaving during the final verification", async () => {
    let resolve!: (value: ContactVerification) => void;
    vi.mocked(context.service.verifyContact)
      .mockResolvedValueOnce(proof())
      .mockImplementationOnce(
        () =>
          new Promise<ContactVerification>((done) => {
            resolve = done;
          }),
      );
    const view = mount();
    await verifyAndCheck();
    fireEvent.click(sendButton());
    expect(context.service.verifyContact).toHaveBeenCalledTimes(2);
    view.unmount();
    await act(async () => resolve(proof()));
    expect(context.service.send).not.toHaveBeenCalled();
    expect(storedAttempts()).toEqual({});
    expect(context.notify).not.toHaveBeenCalled();
  });

  it("does not send an old draft when content changes during the final verification", async () => {
    let resolve!: (value: ContactVerification) => void;
    const oldProof = proof();
    vi.mocked(context.service.verifyContact)
      .mockResolvedValueOnce(oldProof)
      .mockImplementationOnce(
        () =>
          new Promise<ContactVerification>((done) => {
            resolve = done;
          }),
      );
    const view = mount();
    await verifyAndCheck();
    fireEvent.click(sendButton());
    draft = {
      ...draft,
      content: "核验期间修改",
      savedContent: "核验期间修改",
      version: 3,
    };
    view.rerender(
      <SendConfirmation
        row={row}
        draft={draft}
        connection={connection}
        onClose={onClose}
      />,
    );
    await act(async () => resolve(oldProof));
    expect(context.service.send).not.toHaveBeenCalled();
    expect(storedAttempts()).toEqual({});
  });
  it.each(["account", "identity"] as const)(
    "does not send when %s changes during the final verification",
    async (change) => {
      let resolve!: (value: ContactVerification) => void;
      const oldProof = proof();
      vi.mocked(context.service.verifyContact)
        .mockResolvedValueOnce(oldProof)
        .mockImplementationOnce(
          () =>
            new Promise<ContactVerification>((done) => {
              resolve = done;
            }),
        );
      const view = mount();
      await verifyAndCheck();
      fireEvent.click(sendButton());
      if (change === "account")
        connection = { ...connection, status: "EXPIRED" };
      else
        context = {
          ...context,
          session: { authenticated: true, userId: crypto.randomUUID() },
        };
      view.rerender(
        <SendConfirmation
          row={row}
          draft={draft}
          connection={connection}
          onClose={onClose}
        />,
      );
      await act(async () => resolve(oldProof));
      expect(context.service.send).not.toHaveBeenCalled();
      expect(storedAttempts()).toEqual({});
    },
  );

  it.each(["NETWORK_ERROR", "SERVICE_TIMEOUT", "SERVICE_UNAVAILABLE"])(
    "retains the unknown-result lock after %s and reopening the dialog",
    async (code) => {
      context.service.send = vi
        .fn()
        .mockRejectedValue(new ServiceError(code, "测试发送结果未知", 0));
      const view = mount();
      await verifyAndCheck();
      fireEvent.click(sendButton());
      await screen.findByText("测试发送结果未知");
      expect(storedAttempts()[attemptKey()]).toBe("PENDING");
      view.unmount();
      mount();
      expect(
        screen.getByText(
          "此版本发送结果尚待确认，请核对平台记录，避免重复发送。",
        ),
      ).toBeTruthy();
      fireEvent.click(checkbox());
      expect(sendButton().disabled).toBe(true);
      expect(context.service.send).toHaveBeenCalledOnce();
    },
  );

  it("preserves an in-flight lock after leaving and receiving a late unknown failure", async () => {
    let reject!: (reason: unknown) => void;
    context.service.send = vi.fn(
      () =>
        new Promise<{ status: string }>((_done, fail) => {
          reject = fail;
        }),
    );
    const view = mount();
    await verifyAndCheck();
    fireEvent.click(sendButton());
    await waitFor(() => expect(context.service.send).toHaveBeenCalledOnce());
    view.unmount();
    await act(async () =>
      reject(new ServiceError("NETWORK_ERROR", "测试迟到的网络错误")),
    );
    mount();
    expect(sendButton().disabled).toBe(true);
    expect(storedAttempts()[attemptKey()]).toBe("PENDING");
  });
  it("does not bypass an unknown-result lock by reopening a newer draft version", async () => {
    context.service.send = vi
      .fn()
      .mockRejectedValue(new ServiceError("NETWORK_ERROR", "测试结果未知"));
    const view = mount();
    await verifyAndCheck();
    fireEvent.click(sendButton());
    await screen.findByText("测试结果未知");
    view.unmount();
    draft = {
      ...draft,
      version: draft.version + 1,
      content: "另一个测试版本",
      savedContent: "另一个测试版本",
    };
    mount();
    fireEvent.click(checkbox());
    expect(sendButton().disabled).toBe(true);
    expect(storedAttempts()[attemptKey()]).toBe("PENDING");
    expect(context.service.send).toHaveBeenCalledOnce();
  });
  it("retains a pending send after clearing drafts and signing back into the same customer space", async () => {
    const userId = context.session.userId!;
    context.service.send = vi
      .fn()
      .mockRejectedValue(new ServiceError("NETWORK_ERROR", "测试发送结果未知"));
    const view = mount();
    await verifyAndCheck();
    fireEvent.click(sendButton());
    await screen.findByText("测试发送结果未知");
    view.unmount();
    act(() => clearLocalDrafts());
    context = { ...context, session: { authenticated: false } };
    const signedOut = mount();
    expect(sendButton().disabled).toBe(true);
    signedOut.unmount();
    context = { ...context, session: { authenticated: true, userId } };
    mount();
    fireEvent.click(checkbox());
    expect(sendButton().disabled).toBe(true);
    expect(storedAttempts()[attemptKey()]).toBe("PENDING");
    expect(context.service.send).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button", { name: "核验发送条件" })).toBeNull();
  });
  it("retains a confirmed sent-version lock when ordinary drafts are cleared", async () => {
    const view = mount();
    await verifyAndCheck();
    fireEvent.click(sendButton());
    await screen.findByText("此版本内容已发送，不能重复发送。");
    view.unmount();
    act(() => clearLocalDrafts());
    mount();
    fireEvent.click(checkbox());
    expect(sendButton().disabled).toBe(true);
    expect(storedAttempts()[sentKey()]).toBe("SENT");
    expect(context.service.send).toHaveBeenCalledOnce();
  });

  it("unlocks an explicit no-execution rejection and verifies again before retrying", async () => {
    vi.mocked(context.service.send)
      .mockRejectedValueOnce(
        new ServiceError("CAPABILITY_UNAVAILABLE", "测试渠道尚未开通", 501),
      )
      .mockResolvedValueOnce({ status: "SENT" });
    mount();
    await verifyAndCheck();
    fireEvent.click(sendButton());
    await screen.findByText("测试渠道尚未开通");
    expect(storedAttempts()).toEqual({});
    expect(sendButton().disabled).toBe(false);
    expect(context.notify).not.toHaveBeenCalled();
    fireEvent.click(sendButton());
    await screen.findByText("此版本内容已发送，不能重复发送。");
    expect(context.service.verifyContact).toHaveBeenCalledTimes(3);
    expect(context.service.send).toHaveBeenCalledTimes(2);
  });
});
