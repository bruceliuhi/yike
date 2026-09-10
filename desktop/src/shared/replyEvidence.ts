import { z } from "zod";
const uuid = z
    .string()
    .uuid()
    .regex(/^[a-f0-9-]+$/),
  sha = z.string().regex(/^[a-f0-9]{64}$/);
const time = z.string().datetime({ offset: true }),
  text = (max: number) => z.string().min(1).max(max);
const base = {
  schema_version: z.literal("reply-event-v1"),
  event_id: uuid,
  tenant_id: uuid,
  user_id: uuid,
  opportunity_id: uuid,
  source_id: uuid,
  outreach_request_id: uuid,
  profile_version_id: uuid,
  state: z.enum(["ACTIVE", "CORRECTED", "VOID"]),
  observed_at: time,
  corrects_event_id: uuid.nullable(),
  reason: text(1024).nullable(),
};
const platformEvent = z
  .object({
    ...base,
    kind: z.literal("PLATFORM_REPLY"),
    platform: z.enum([
      "XIAOHONGSHU",
      "DOUYIN",
      "BILIBILI",
      "ZHIHU",
      "PUBLIC_WEB",
    ]),
    channel: z.enum(["comment", "dm"]),
    external_reply_id: text(512),
    sender_public_id: text(512),
    body: text(120000),
    received_at: time,
    read_state: z.enum(["UNREAD", "READ", "UNKNOWN"]),
    read_at: time.nullable(),
  })
  .strict();
const manualEvent = z
  .object({
    ...base,
    kind: z.literal("MANUAL_FOLLOWUP"),
    action: z.enum(["CONTACTED", "MEETING", "QUOTED", "LOST", "WON", "NOTE"]),
    note: text(120000),
    occurred_at: time,
  })
  .strict();
const verification = z.discriminatedUnion("authority", [
  z.object({ authority: z.literal("MANUAL_RECORD") }).strict(),
  z.object({ authority: z.literal("OPERATOR_RECORDED") }).strict(),
  z
    .object({
      authority: z.literal("DEVICE_ATTESTED_PLATFORM_REPLY"),
      schemaVersion: z.literal("device-reply-attestation-v1"),
      deviceId: uuid,
      credentialVersion: z.number().int().positive(),
      claimId: uuid,
      contextSha256: sha,
      requestSha256: sha,
      replyEventSha256: sha,
      verifiedAt: time,
    })
    .strict(),
]);
const rowSchema = z
  .object({
    revision: z.number().int().positive().max(2147483647),
    event: z.discriminatedUnion("kind", [platformEvent, manualEvent]),
    verification,
  })
  .strict();
export type ReplyEvidence = z.infer<typeof rowSchema>;
type PlatformRow = ReplyEvidence & { event: z.infer<typeof platformEvent> };
export type ReplyEvidenceScope = {
  userId: string;
  tenantId: string;
  opportunityId: string;
};
export function readReplyEvidence(raw: unknown, scope: ReplyEvidenceScope) {
  try {
    const history = z.array(rowSchema).max(10000).parse(raw),
      versions = new Set<string>(),
      platformVersions = new Set<string>();
    const current = new Map<string, PlatformRow>();
    for (const row of history) {
      const e = row.event,
        v = row.verification,
        observed = Date.parse(e.observed_at);
      if (
        e.user_id !== scope.userId ||
        e.tenant_id !== scope.tenantId ||
        e.opportunity_id !== scope.opportunityId
      )
        throw Error();
      const key = JSON.stringify([e.event_id, row.revision]);
      if (versions.has(key)) throw Error();
      versions.add(key);
      if (
        e.state === "ACTIVE"
          ? e.corrects_event_id !== null || e.reason !== null
          : !e.corrects_event_id || !e.reason?.trim()
      )
        throw Error();
      if (e.kind === "MANUAL_FOLLOWUP") {
        if (
          v.authority !== "MANUAL_RECORD" ||
          Date.parse(e.occurred_at) > observed
        )
          throw Error();
      } else {
        if (
          v.authority === "MANUAL_RECORD" ||
          Date.parse(e.received_at) > observed ||
          (e.read_state === "READ" ? !e.read_at : e.read_at !== null) ||
          (e.read_at &&
            (Date.parse(e.read_at) < Date.parse(e.received_at) ||
              Date.parse(e.read_at) > observed))
        )
          throw Error();
        const identity = JSON.stringify([
          e.source_id,
          e.outreach_request_id,
          e.platform,
          e.external_reply_id,
        ]);
        const version = JSON.stringify([identity, row.revision]);
        if (platformVersions.has(version)) throw Error();
        platformVersions.add(version);
        const previous = current.get(identity);
        if (
          previous &&
          (previous.event.sender_public_id !== e.sender_public_id ||
            previous.event.channel !== e.channel ||
            previous.event.profile_version_id !== e.profile_version_id)
        )
          throw Error();
        if (!previous || previous.revision < row.revision)
          current.set(identity, { ...row, event: e });
      }
    }
    history.sort(
      (a, b) =>
        Date.parse(b.event.observed_at) - Date.parse(a.event.observed_at) ||
        b.revision - a.revision,
    );
    return {
      history,
      replies: [...current.values()].sort(
        (a, b) =>
          Date.parse(b.event.received_at) - Date.parse(a.event.received_at),
      ),
      manual: history.filter((row) => row.event.kind === "MANUAL_FOLLOWUP"),
    };
  } catch {
    throw new Error("回复证据格式或归属不匹配，请刷新核对。");
  }
}
