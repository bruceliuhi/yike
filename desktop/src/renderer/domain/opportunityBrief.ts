import { z } from "zod";
import { explicitInstant } from "./opportunityLibrary";

const id = z
  .string()
  .trim()
  .min(1)
  .max(128)
  .refine(
    (value) =>
      value !== "sample" &&
      !value.startsWith("sample:") &&
      !/[\u0000-\u001f\u007f]/.test(value),
  );
const revision = z.number().int().positive().max(Number.MAX_SAFE_INTEGER);
const instant = z.string().refine(explicitInstant);
const text = z.string().trim().min(1).max(4000);
const day = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/)
  .refine((value) => explicitInstant(`${value}T00:00:00Z`));
const timezone = z
  .string()
  .min(1)
  .max(100)
  .refine((value) => {
    try {
      new Intl.DateTimeFormat("zh-CN", { timeZone: value });
      return true;
    } catch {
      return false;
    }
  });
export const briefQuerySchema = z
  .object({
    contractVersion: z.literal(1),
    requestId: id,
    userId: id,
    accountScopeId: id,
    scopeVersion: revision,
    profileId: id,
    profileVersion: revision,
    businessDate: day,
    timezone,
  })
  .strict();
const basis = z
  .object({
    recordId: id,
    version: id,
    excerpt: text,
    kind: z.enum([
      "REVIEWED_DEMAND",
      "VERIFIED_CHANGE",
      "MANUAL_FOLLOWUP",
      "CHANNEL_FOLLOWUP",
    ]),
    verifiedAt: instant,
  })
  .strict();
const itemSchema = z
  .object({
    id,
    opportunityId: id,
    opportunityVersion: id,
    title: z.string().trim().min(1).max(300),
    reason: text,
    profileId: id,
    profileVersion: revision,
    sample: z.literal(false),
    validity: z.enum(["VALID", "EXPIRED", "TARGET_MISSING"]),
    basis,
  })
  .strict();
const groupSchema = z
  .object({
    items: z.array(itemSchema).max(1000),
    total: z.number().int().nonnegative().max(1000),
  })
  .strict();
const snapshotSchema = briefQuerySchema
  .extend({
    snapshotId: id,
    audience: z.literal("CUSTOMER"),
    generatedAt: instant,
    expiresAt: instant,
    coverage: z.enum(["NOT_CHECKED", "PARTIAL", "COMPLETE"]),
    lastCompletedCheckAt: instant.nullable(),
    checkedScope: z.array(text).max(100),
    uncheckedScope: z.array(text).max(100),
    runs: z
      .array(z.object({ taskId: id, runId: id, windowId: id }).strict())
      .max(100),
    groups: z
      .object({
        contact: groupSchema,
        changes: groupSchema,
        followup: groupSchema,
      })
      .strict(),
  })
  .strict();
export type BriefQuery = z.infer<typeof briefQuerySchema>;
export type OpportunityBriefSnapshot = z.infer<typeof snapshotSchema>;
export type BriefItem = z.infer<typeof itemSchema>;
export type BriefGroup = keyof OpportunityBriefSnapshot["groups"];
export const briefGroupLabels: Record<BriefGroup, string> = {
  contact: "今日值得联系",
  changes: "重要变化",
  followup: "待跟进",
};

/** Read-only snapshot bound to the authenticated account, one confirmed profile,
 * and an explicit business day. Group totals are never summed as new customers. */
export function parseOpportunityBrief(
  value: unknown,
  expected: BriefQuery,
  now = Date.now(),
): OpportunityBriefSnapshot {
  const query = briefQuerySchema.parse(expected);
  const parsed = snapshotSchema.safeParse(value);
  if (!parsed.success)
    throw new Error("简报数据不完整、包含样例或版本不受支持，请重新读取。");
  const snapshot = parsed.data;
  if (
    (Object.keys(query) as (keyof BriefQuery)[]).some(
      (key) => snapshot[key] !== query[key],
    )
  )
    throw new Error("简报与当前账户、画像或业务日期不一致，请刷新重试。");
  if (
    Date.parse(snapshot.generatedAt) > now ||
    Date.parse(snapshot.generatedAt) >= Date.parse(snapshot.expiresAt) ||
    (snapshot.lastCompletedCheckAt !== null &&
      Date.parse(snapshot.lastCompletedCheckAt) >
        Date.parse(snapshot.generatedAt)) ||
    (snapshot.coverage === "COMPLETE" &&
      (!snapshot.lastCompletedCheckAt ||
        !snapshot.checkedScope.length ||
        snapshot.uncheckedScope.length)) ||
    (snapshot.coverage === "PARTIAL" && !snapshot.uncheckedScope.length) ||
    new Set(
      snapshot.runs.map((run) => `${run.taskId}:${run.runId}:${run.windowId}`),
    ).size !== snapshot.runs.length
  )
    throw new Error("简报检查范围或时效不一致，不能判断今日结果。");
  for (const [kind, group] of Object.entries(snapshot.groups) as [
    BriefGroup,
    OpportunityBriefSnapshot["groups"][BriefGroup],
  ][]) {
    if (
      group.items.length !== group.total ||
      new Set(group.items.map((item) => item.id)).size !== group.items.length ||
      new Set(group.items.map((item) => item.opportunityId)).size !==
        group.items.length
    )
      throw new Error("简报分组计数或对象重复，请刷新核对明细。");
    for (const item of group.items) {
      if (
        item.profileId !== query.profileId ||
        item.profileVersion !== query.profileVersion ||
        (kind === "contact" && item.basis.kind !== "REVIEWED_DEMAND") ||
        (kind === "changes" && item.basis.kind !== "VERIFIED_CHANGE") ||
        (kind === "followup" &&
          !["MANUAL_FOLLOWUP", "CHANNEL_FOLLOWUP"].includes(item.basis.kind)) ||
        Date.parse(item.basis.verifiedAt) > Date.parse(snapshot.generatedAt)
      )
        throw new Error("简报条目缺少同画像的需求、变化或跟进依据。");
    }
  }
  if (
    snapshot.coverage === "NOT_CHECKED" &&
    (snapshot.checkedScope.length ||
      snapshot.runs.length ||
      Object.values(snapshot.groups).some((group) => group.total))
  )
    throw new Error("尚未检查的简报不能包含已核验机会或运行结果。");
  return snapshot;
}

export function briefBusinessDay(at: number, timeZone: string) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(at));
  const part = (type: string) =>
    parts.find((value) => value.type === type)!.value;
  return `${part("year")}-${part("month")}-${part("day")}`;
}
/** Locate the next calendar-day boundary in the selected zone, including DST. */
export function nextBriefDay(at: number, timeZone: string) {
  const current = briefBusinessDay(at, timeZone);
  let low = at,
    high = at + 36 * 60 * 60 * 1000;
  while (high - low > 1) {
    const middle = Math.floor((low + high) / 2);
    if (briefBusinessDay(middle, timeZone) === current) low = middle;
    else high = middle;
  }
  return high;
}
export function briefTarget(kind: BriefGroup, item: BriefItem) {
  if (item.validity !== "VALID") return null;
  return kind === "followup"
    ? `/followups?tab=todo&opportunity=${encodeURIComponent(item.opportunityId)}`
    : `/opportunities/${encodeURIComponent(item.opportunityId)}`;
}
