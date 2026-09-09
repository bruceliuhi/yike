// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  OutreachPage,
  contactFingerprint,
} from "../../src/renderer/pages/Outreach";
import { PUBLIC_SAMPLE } from "../../src/renderer/pages/Opportunities";
import { parseRoute } from "../../src/renderer/domain/routes";
import type { AppContextValue } from "../../src/renderer/app/context";
import type { ContactDraft } from "../../src/renderer/domain/models";
import {
  ServiceError,
  type YikeService,
} from "../../src/renderer/services/contracts";
let context: AppContextValue;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => context }));
beforeEach(() => {
  sessionStorage.clear();
  context = {
    service: {
      opportunities: vi.fn().mockResolvedValue([]),
      opportunity: vi.fn(),
      connections: vi.fn().mockResolvedValue([]),
      saveContact: vi
        .fn()
        .mockRejectedValue(
          new ServiceError("UNAVAILABLE", "草稿同步尚未接通", 501),
        ),
      generateContact: vi
        .fn()
        .mockRejectedValue(
          new ServiceError("UNAVAILABLE", "生成服务尚未接通", 501),
        ),
      send: vi.fn(),
      copy: vi.fn().mockResolvedValue(undefined),
    } as unknown as YikeService,
    session: { authenticated: true, userId: crypto.randomUUID() },
    route: parseRoute("#/outreach?opportunity=sample&confirm=send"),
    navigate: vi.fn(),
    notify: vi.fn(),
    refreshSession: vi.fn(),
  };
});
afterEach(cleanup);
describe("contact preparation and confirmation", () => {
  it("never unlocks sample writing or sending after confirmation is checked", async () => {
    render(<OutreachPage />);
    await screen.findByRole("dialog", { name: "确认发送" });
    expect(
      (screen.getByRole("textbox", { name: "沟通内容" }) as HTMLTextAreaElement)
        .readOnly,
    ).toBe(true);
    expect(
      (screen.getByRole("button", { name: "保存草稿" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "我已核对联系对象、发送账号和内容",
      }),
    );
    expect(
      (screen.getByRole("button", { name: "确认并发送" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(context.service.send).not.toHaveBeenCalled();
    expect(context.service.saveContact).not.toHaveBeenCalled();
  });
  it("retains manual text when saving fails and isolates comment from dm edits", async () => {
    const opportunity = {
      ...PUBLIC_SAMPLE,
      id: "customer-a",
      sample: false,
      profileStatus: "CONFIRMED",
      sourceStatus: "OPEN",
      profileVersionId: "profile-a",
      comment: "已有评论草稿",
      dm: "已有私信草稿",
    };
    context.route = parseRoute("#/outreach?opportunity=customer-a");
    context.service.opportunity = vi.fn().mockResolvedValue(opportunity);
    render(<OutreachPage />);
    await screen.findByDisplayValue("已有评论草稿");
    fireEvent.change(screen.getByRole("textbox", { name: "沟通内容" }), {
      target: { value: "人工保留内容" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
    await screen.findByText("草稿同步尚未接通");
    expect(
      (screen.getByRole("textbox", { name: "沟通内容" }) as HTMLTextAreaElement)
        .value,
    ).toBe("人工保留内容");
    fireEvent.click(screen.getByRole("tab", { name: "私信草稿" }));
    expect(
      (screen.getByRole("textbox", { name: "沟通内容" }) as HTMLTextAreaElement)
        .value,
    ).toBe("已有私信草稿");
    fireEvent.click(screen.getByRole("tab", { name: "评论草稿" }));
    expect(
      (screen.getByRole("textbox", { name: "沟通内容" }) as HTMLTextAreaElement)
        .value,
    ).toBe("人工保留内容");
    expect(context.service.send).not.toHaveBeenCalled();
  });
  it("does not carry locally edited customer content to another signed-in identity", async () => {
    const opportunity = {
      ...PUBLIC_SAMPLE,
      id: "same-id",
      sample: false,
      comment: "服务端草稿",
    };
    context.route = parseRoute("#/outreach?opportunity=same-id");
    context.service.opportunity = vi.fn().mockResolvedValue(opportunity);
    const view = render(<OutreachPage />);
    await screen.findByDisplayValue("服务端草稿");
    fireEvent.change(screen.getByRole("textbox", { name: "沟通内容" }), {
      target: { value: "客户A的编辑" },
    });
    context = {
      ...context,
      session: { authenticated: true, userId: "another-customer" },
    };
    view.rerender(<OutreachPage />);
    await waitFor(() =>
      expect(
        (
          screen.getByRole("textbox", {
            name: "沟通内容",
          }) as HTMLTextAreaElement
        ).value,
      ).toBe("服务端草稿"),
    );
  });
  it("binds confirmation to content, purpose, account, recipient and source version", () => {
    const draft: ContactDraft = {
      opportunityId: "real",
      channel: "comment",
      content: "全文",
      savedContent: "全文",
      version: 1,
      accountId: "account-a",
      recipient: "recipient-a",
    };
    const row = { ...PUBLIC_SAMPLE, id: "real", sample: false };
    const original = contactFingerprint(draft, row);
    for (const change of [
      { content: "修改" },
      { channel: "dm" as const },
      { accountId: "b" },
      { recipient: "b" },
      { version: 2 },
    ])
      expect(contactFingerprint({ ...draft, ...change }, row)).not.toBe(
        original,
      );
    expect(
      contactFingerprint(draft, { ...row, profileVersionId: "changed" }),
    ).not.toBe(original);
  });
});
