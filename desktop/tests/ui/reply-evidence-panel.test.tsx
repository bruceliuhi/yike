// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { ReplyEvidencePanel } from "../../src/renderer/pages/followups/ReplyEvidencePanel";
import { service as realService } from "../../src/renderer/services/client";
import { PUBLIC_SAMPLE } from "../../src/renderer/pages/Opportunities";
let app: any;
vi.mock("../../src/renderer/app/context", () => ({ useApp: () => app }));
const id = () => crypto.randomUUID();
function fixture() {
  const opportunity = { ...PUBLIC_SAMPLE, id: id(), sample: false };
  app = {
    session: {
      authenticated: true,
      userId: id(),
      accountScope: { id: id(), version: 1 },
    },
    service: { replyEvidence: vi.fn() },
  };
  const row = {
    revision: 1,
    event: {
      schema_version: "reply-event-v1",
      event_id: id(),
      user_id: app.session.userId,
      tenant_id: app.session.accountScope.id,
      opportunity_id: opportunity.id,
      source_id: id(),
      outreach_request_id: id(),
      profile_version_id: id(),
      state: "ACTIVE",
      observed_at: "2026-09-12T01:00:00Z",
      corrects_event_id: null,
      reason: null,
      kind: "PLATFORM_REPLY",
      platform: "XIAOHONGSHU",
      channel: "comment",
      external_reply_id: "reply1",
      sender_public_id: "buyer1",
      body: "想先看案例",
      received_at: "2026-09-12T00:59:00Z",
      read_state: "UNKNOWN",
      read_at: null,
    },
    verification: { authority: "OPERATOR_RECORDED" },
  };
  return { opportunity, row };
}
afterEach(() => {
  cleanup();
  delete (window as any).yikeDesktop;
});
it("shows original evidence and unknown read state without presenting an action to send or mark read", async () => {
  const f = fixture();
  app.service.replyEvidence.mockResolvedValue([f.row]);
  render(<ReplyEvidencePanel opportunity={f.opportunity} />);
  expect(await screen.findByText("想先看案例")).toBeTruthy();
  expect(screen.getByText("历史人工录入 · 非设备证明")).toBeTruthy();
  expect(screen.getByText("已读状态未知")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "标为已读" })).toBeNull();
  expect(screen.queryByRole("button", { name: "发送" })).toBeNull();
});
it("keeps failures distinct from an empty platform inbox", async () => {
  const f = fixture();
  app.service.replyEvidence.mockRejectedValue(Error("读取失败"));
  render(<ReplyEvidencePanel opportunity={f.opportunity} />);
  expect(await screen.findByText("读取失败")).toBeTruthy();
  expect(screen.queryByText("暂无保存的回复证据")).toBeNull();
});
it("ignores the previous account late response after switching identity", async () => {
  const f = fixture();
  let resolve!: (rows: unknown) => void;
  app.service.replyEvidence.mockReturnValueOnce(
    new Promise((r) => {
      resolve = r;
    }),
  );
  const view = render(<ReplyEvidencePanel opportunity={f.opportunity} />);
  await waitFor(() =>
    expect(app.service.replyEvidence).toHaveBeenCalledTimes(1),
  );
  app = { ...app, session: { ...app.session, userId: id() } };
  app.service.replyEvidence.mockResolvedValue([]);
  view.rerender(<ReplyEvidencePanel opportunity={f.opportunity} />);
  await screen.findByText("暂无保存的回复证据");
  await act(async () => resolve([f.row]));
  expect(screen.queryByText("想先看案例")).toBeNull();
});
it("ordinary desktop service preserves the actual evidence array through the fixed read operation", async () => {
  const f = fixture(),
    requestApi = vi.fn(async () => ({ ok: true, status: 200, data: [f.row] }));
  (window as any).yikeDesktop = { requestApi };
  expect(await realService.replyEvidence!(f.opportunity.id)).toEqual([f.row]);
  expect(requestApi).toHaveBeenCalledWith({
    operation: "replies.evidence",
    payload: { opportunityId: f.opportunity.id },
  });
});
