// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { webcrypto } from "node:crypto";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AppProvider } from "../../src/renderer/app/context";
import { clearLocalDrafts } from "../../src/renderer/app/hooks";
import { FollowupsPage } from "../../src/renderer/pages/Followups";
import { PUBLIC_SAMPLE } from "../../src/renderer/pages/Opportunities";
import { service as base } from "../../src/renderer/services/client";
import type { FollowupMutation, FollowupRecord, LinkedReply } from "../../src/renderer/domain/followup";

const opportunity = { ...PUBLIC_SAMPLE, id: "TEST-reply-flow", sample: false,
  title: "TEST无人工记录的回复商机", profileVersionId: "TEST-profile-v1" };
beforeEach(() => {
  vi.stubGlobal("crypto", webcrypto);
  clearLocalDrafts(); localStorage.clear(); sessionStorage.clear();
  history.replaceState(null, "", `#/followups?opportunity=${opportunity.id}&tab=replies`);
});
afterEach(() => { cleanup(); clearLocalDrafts(); vi.unstubAllGlobals(); });
function mount(options: { replyError?: boolean; recordsError?: boolean } = {}) {
  const records: FollowupRecord[] = [];
  let reply: LinkedReply = { id: "TEST-reply-flow-event", revision: 1,
    opportunityId: opportunity.id, profileVersionId: opportunity.profileVersionId,
    sendRequestId: "TEST-original-send", platform: "douyin", content: "TEST合成渠道回复",
    receivedAt: "2026-09-10T01:00:00Z", read: false, sample: false };
  const service = { ...base,
    session: vi.fn().mockResolvedValue({ authenticated: true, userId: "TEST-member",
      accountScope: { id: "TEST-space", version: 1 } }),
    opportunities: vi.fn().mockResolvedValue([]),
    opportunity: vi.fn().mockImplementation(async (id: string) => {
      if (id !== opportunity.id) throw new Error("TEST商机不存在");
      return opportunity;
    }),
    followup: {
      list: vi.fn().mockImplementation(async () => {
        if (options.recordsError) throw new Error("TEST人工记录读取失败");
        return { records: [...records], members: [{ id: "TEST-member", name: "TEST成员" }] };
      }),
      replies: vi.fn().mockImplementation(async (id?: string) => {
        if (options.replyError) throw new Error("TEST渠道暂时不可读");
        return id === opportunity.id ? [reply] : [];
      }),
      mutate: vi.fn().mockImplementation(async (input: FollowupMutation) => {
        if (input.binding.action === "mark-read") {
          reply = { ...reply, read: true, revision: reply.revision + 1 };
          return { binding: input.binding, status: "SUCCEEDED" as const, confirmed: true, reply };
        }
        if (input.binding.action !== "create" || !input.values) throw new Error("TEST不支持该操作");
        const record: FollowupRecord = { ...input.values, id: "TEST-created-followup", revision: 1,
          opportunityId: opportunity.id, profileVersionId: opportunity.profileVersionId,
          title: opportunity.title, createdAt: new Date().toISOString(), kind: "manual",
          ownerName: "TEST成员", state: "ACTIVE", sample: false, replyCount: 1 };
        records.push(record);
        return { binding: input.binding, status: "SUCCEEDED" as const, confirmed: true, record };
      }),
      operation: vi.fn(),
    },
  };
  render(<AppProvider service={service}><FollowupsPage /></AppProvider>);
  return { service, records };
}
async function editor() {
  fireEvent.click(screen.getByRole("button", { name: "添加跟进" }));
  return within(await screen.findByRole("dialog", { name: "添加跟进" }));
}
it("adds a fact for an exact accessible detail outside the list and returns to its replies", async () => {
  const { service, records } = mount();
  await screen.findByText("TEST合成渠道回复");
  expect(records).toHaveLength(0);
  const form = await editor();
  expect(form.getByRole("combobox", { name: "关联商机" })).toHaveValue(opportunity.id);
  fireEvent.click(form.getByRole("radio", { name: "已联系" }));
  fireEvent.change(form.getByRole("textbox", { name: "跟进备注" }), { target: { value: "TEST已核对回复，下次补充资料" } });
  fireEvent.click(form.getByRole("button", { name: "保存记录" }));
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "添加跟进" })).toBeNull());
  expect(service.followup.mutate).toHaveBeenCalledOnce();
  expect(records).toHaveLength(1);
  expect(location.hash).toContain(`opportunity=${opportunity.id}`);
  expect(location.hash).toContain("tab=replies");
  expect(location.hash).not.toContain("add=1");
  fireEvent.click(screen.getByRole("tab", { name: "人工登记" }));
  await screen.findByText("TEST已核对回复，下次补充资料");
});
it("keeps the target and unsaved draft when explicitly closing and reopening the editor", async () => {
  const { service } = mount();
  await screen.findByText("TEST合成渠道回复");
  const form = await editor();
  fireEvent.change(form.getByRole("textbox", { name: "跟进备注" }), { target: { value: "TEST保留的人工输入" } });
  fireEvent.click(form.getByRole("button", { name: "取消" }));
  const confirmation = within(await screen.findByRole("dialog", { name: "保留未保存内容并关闭？" }));
  fireEvent.click(confirmation.getByRole("button", { name: "保留并关闭" }));
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "添加跟进" })).toBeNull());
  expect(location.hash).toContain(`opportunity=${opportunity.id}`);
  const reopened = await editor();
  expect(reopened.getByRole("textbox", { name: "跟进备注" })).toHaveValue("TEST保留的人工输入");
  expect(service.followup.mutate).not.toHaveBeenCalled();
});
it("marks a matched reply read without first manufacturing a manual record", async () => {
  const { service, records } = mount();
  await screen.findByText("TEST合成渠道回复");
  fireEvent.click(screen.getByRole("button", { name: "标为已读" }));
  await screen.findByText("已读");
  expect(records).toHaveLength(0);
  expect(service.followup.mutate).toHaveBeenCalledOnce();
  expect(service.followup.mutate.mock.calls[0][0].binding).toMatchObject({
    opportunityId: opportunity.id, profileVersionId: opportunity.profileVersionId, action: "mark-read",
    targetId: "TEST-reply-flow-event", targetRevision: 1,
  });
});
it("does not let manual-list filters silently replace the selected reply target with unmatched replies", async () => {
  const { service } = mount();
  await screen.findByText("TEST合成渠道回复");
  fireEvent.change(screen.getByLabelText("筛选记录日期"), { target: { value: "2026-09-01" } });
  fireEvent.click(screen.getByRole("tab", { name: "全部" }));
  expect(screen.getByText("TEST合成渠道回复")).toBeVisible();
  expect(screen.getByRole("combobox", { name: "查看商机回复" })).toHaveValue(opportunity.id);
  expect(service.followup.replies.mock.calls.every(([id]) => id === opportunity.id)).toBe(true);
});
it("allows viewing empty manual history and adding a fact while the independent reply read fails", async () => {
  mount({ replyError: true });
  await screen.findByText("TEST渠道暂时不可读");
  fireEvent.click(screen.getByRole("tab", { name: "人工登记" }));
  expect(screen.getByText("暂无关联登记")).toBeVisible();
  const form = await editor();
  expect(form.getByRole("combobox", { name: "关联商机" })).toHaveValue(opportunity.id);
});
it("does not turn an unavailable manual history into a false empty state", async () => {
  mount({ recordsError: true });
  await screen.findByText("TEST合成渠道回复");
  fireEvent.click(screen.getByRole("tab", { name: "人工登记" }));
  expect(screen.queryByText("暂无关联登记")).toBeNull();
  expect(screen.getAllByText("TEST人工记录读取失败").length).toBeGreaterThan(0);
});
