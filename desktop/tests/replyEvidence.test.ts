import { expect, it } from "vitest";
import { randomUUID } from "node:crypto";
import { readReplyEvidence } from "../src/shared/replyEvidence";
import { validatedOperation } from "../src/main/servicePolicy";
const id = () => randomUUID();
function fixture() {
  const scope = { userId: id(), tenantId: id(), opportunityId: id() };
  return {
    scope,
    row: {
      revision: 1,
      event: {
        schema_version: "reply-event-v1",
        event_id: id(),
        user_id: scope.userId,
        tenant_id: scope.tenantId,
        opportunity_id: scope.opportunityId,
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
        external_reply_id: "reply123",
        sender_public_id: "author123",
        body: "请发个方案",
        received_at: "2026-09-12T00:59:00Z",
        read_state: "UNREAD",
        read_at: null,
      },
      verification: { authority: "OPERATOR_RECORDED" },
    },
  };
}
it("folds read revisions without counting them as new replies and preserves original history", () => {
  const { scope, row } = fixture();
  const read = {
    ...row,
    revision: 2,
    event: {
      ...row.event,
      read_state: "READ",
      read_at: "2026-09-12T01:01:00Z",
      observed_at: "2026-09-12T01:01:00Z",
    },
  };
  const result = readReplyEvidence([read, row], scope);
  expect(result.replies).toHaveLength(1);
  expect(result.history).toHaveLength(2);
  expect(result.replies[0].event.read_state).toBe("READ");
});
it.each([
  "owner",
  "tenant",
  "opportunity",
  "duplicate",
  "manual-proof",
  "unknown-authority",
])("rejects %s mismatch instead of returning empty", (reason) => {
  const { scope, row } = fixture();
  let raw: any[] = [row];
  if (reason === "owner") row.event.user_id = id();
  if (reason === "tenant") row.event.tenant_id = id();
  if (reason === "opportunity") row.event.opportunity_id = id();
  if (reason === "duplicate") raw = [row, row];
  if (reason === "manual-proof") row.verification.authority = "MANUAL_RECORD";
  if (reason === "unknown-authority") row.verification.authority = "VERIFIED";
  expect(() => readReplyEvidence(raw, scope)).toThrow(
    "回复证据格式或归属不匹配",
  );
});
it("exposes only the fixed authenticated evidence read route", () => {
  const opportunityId = id();
  expect(
    validatedOperation({
      operation: "replies.evidence",
      payload: { opportunityId },
    }),
  ).toEqual({
    path: `/api/ui/opportunities/${opportunityId}/replies/evidence`,
    method: "GET",
    logout: false,
  });
  expect(
    validatedOperation({
      operation: "replies.evidence",
      payload: { opportunityId, tenantId: id() },
    }),
  ).toBeNull();
  expect(
    validatedOperation({
      operation: "replies.evidence",
      payload: { opportunityId: "../private" },
    }),
  ).toBeNull();
});
