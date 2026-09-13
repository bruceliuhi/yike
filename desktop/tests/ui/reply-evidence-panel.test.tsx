// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ReplyEvidencePanel } from "../../src/renderer/pages/followups/ReplyEvidencePanel";
import { RelatedReplies } from "../../src/renderer/pages/followups/RelatedReplies";
import { service as realService } from "../../src/renderer/services/client";
import { PUBLIC_SAMPLE } from "../../src/renderer/pages/Opportunities";
import { nativeOutreachLedgerKey, writeNativeOutreachRecord } from "../../src/renderer/pages/outreach/nativeOutreachLedger";
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
  localStorage.clear();
  delete (window as any).yikeDesktop;
});
it('omits internal reply associations while preserving author, original body and unknown read state', async () => {
  const {opportunity,row}=fixture();app.service.replyEvidence.mockResolvedValue([row]);
  render(<ReplyEvidencePanel opportunity={opportunity}/>);
  await screen.findByText(row.event.body);
  expect(screen.queryByText('原始关联')).toBeNull();
  for(const value of [row.event.source_id,row.event.outreach_request_id,row.event.profile_version_id,row.event.event_id]) expect(screen.queryByText(value,{exact:false})).toBeNull();
  expect(screen.getByText('已读状态未知')).toBeTruthy();
  expect(screen.getByText(/buyer1/)).toBeTruthy();
});
it.each(['session', 'token', 'sms'])('ordinary %s identity reaches selected opportunity evidence', async (method) => {
  const f = fixture();
  const requestApi = vi.fn(async (request: any) => ({ok: true, status: 200, data:
    request.operation === 'replies.evidence' ? [f.row] : request.operation === 'followup.replies' ? [] : {
      authenticated: true, user_id: f.row.event.user_id,
      account_scope: {id: f.row.event.tenant_id, version: 1},
    }}));
  (window as any).yikeDesktop = {requestApi};
  const session = method === 'session' ? await realService.session() : method === 'token'
    ? await realService.loginToken!('test-token') : await realService.login('13800000000', '123456');
  app = {session, service: {...realService, opportunity: vi.fn(async () => f.opportunity)}};
  render(<RelatedReplies opportunityId={f.opportunity.id} choices={[f.opportunity]} choicesLoading={false} choicesError=""
    onReloadChoices={vi.fn()} onSelect={vi.fn()} onResolved={vi.fn()} records={[]} recordsLoading={false} recordsError="" onCorrect={vi.fn()} onChanged={vi.fn()} />);
  expect(session).toMatchObject({authenticated:true,userId:f.row.event.user_id,accountScope:{id:f.row.event.tenant_id,version:1}});
  fireEvent.click(await screen.findByRole('button', {name:'查看原始回复证据与同步'}));
  expect(await screen.findByText('想先看案例')).toBeTruthy();
  expect(requestApi).toHaveBeenCalledWith({operation: 'replies.evidence', payload: {opportunityId: f.opportunity.id}});
  expect(requestApi.mock.calls.some(([input]) => /mutate|dispatch|sync|mark-read/.test(input.operation))).toBe(false);
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
it("keeps the native sync result visible while its evidence reload is pending", async () => {
  const f = fixture(), requestId = id();
  f.opportunity.platform = "xhs";
  writeNativeOutreachRecord(nativeOutreachLedgerKey(app.session, f.opportunity.id, "comment"), {
    state: "PENDING",
    binding: {tenantId: app.session.accountScope.id, requestId, claimId: id(), contextSha256: "a".repeat(64)},
  });
  let finishReload!: (rows: unknown[]) => void;
  app.service.replyEvidence
    .mockResolvedValueOnce([])
    .mockReturnValueOnce(new Promise((resolve) => { finishReload = resolve; }));
  const nativeReplyCommand = vi.fn().mockResolvedValue({state: "SYNCED", requestId, coverage: "PARTIAL", observed: 2, recorded: 1});
  Object.defineProperty(window, "yikeDesktop", {configurable: true, value: {nativeReplyCommand}});
  render(<ReplyEvidencePanel opportunity={f.opportunity} />);
  fireEvent.click(await screen.findByRole("button", {name: "同步此联系的回复"}));
  expect(await screen.findByText("部分范围读取：2 条；保存并核实：1 条（包含去重结果）。")).toBeTruthy();
  expect(app.service.replyEvidence).toHaveBeenCalledTimes(2);
  expect(screen.getByText("部分范围读取：2 条；保存并核实：1 条（包含去重结果）。")).toBeTruthy();
  await act(async () => finishReload([]));
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
