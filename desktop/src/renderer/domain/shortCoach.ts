import { z } from "zod";
import type { ContactDraft, Opportunity } from "./models";
import { explicitInstant } from "./opportunityLibrary";

const id = z.string().trim().min(1).max(128);
const body = z
  .string()
  .min(1)
  .max(8000)
  .refine((v) => !!v.trim() && !v.includes("\0"));
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const instant = z.string().refine(explicitInstant);
const accountScopeSchema = z
  .object({ id, version: z.number().int().min(1) })
  .strict();
export type CoachAccountScope = z.infer<typeof accountScopeSchema>;
const url = z
  .string()
  .max(2048)
  .refine((value) => {
    try {
      const parsed = new URL(value);
      return (
        ["https:", "http:"].includes(parsed.protocol) &&
        !parsed.username &&
        !parsed.password
      );
    } catch {
      return false;
    }
  });
export const COACH_PURPOSES = {
  requirement: "确认具体需求",
  materials: "询问资料获取方式",
  scope: "确认服务范围",
} as const;
export type CoachPurpose = keyof typeof COACH_PURPOSES;
export const coachBindingSchema = z
  .object({
    accountScope: accountScopeSchema,
    requestId: id,
    opportunityId: id,
    profileVersionId: id,
    sourceEvidenceVersion: id,
    sourceUrl: url,
    sourceObservedAt: instant,
    channel: z.enum(["comment", "dm"]),
    draftVersion: z.number().int().min(1),
    draftHash: hash,
    purpose: z.enum(["requirement", "materials", "scope"]),
  })
  .strict();
export type CoachBinding = z.infer<typeof coachBindingSchema>;
export interface CoachInput {
  binding: CoachBinding;
  content: string;
  sourceText: string;
}
const quoteSchema = z
  .object({
    id,
    text: body,
    start: z.number().int().min(0),
    end: z.number().int().min(1),
    sourceUrl: url,
    sourceEvidenceVersion: id,
  })
  .strict();
export const coachSuggestionSchema = z
  .object({
    suggestionId: id,
    binding: coachBindingSchema,
    content: body,
    question: body,
    context: z
      .object({ summary: body, quoteIds: z.array(id).min(1).max(12) })
      .strict(),
    quotes: z.array(quoteSchema).min(1).max(12),
    checks: z
      .array(
        z
          .object({
            kind: z.enum(["CONTEXT", "ONE_QUESTION", "PROMISE", "LENGTH"]),
            status: z.enum(["SUPPORTED", "NEEDS_REVIEW"]),
            message: body,
            quoteIds: z.array(id).max(12),
          })
          .strict(),
      )
      .max(12),
    createdAt: instant,
    expiresAt: instant,
  })
  .strict();
export type CoachSuggestion = z.infer<typeof coachSuggestionSchema>;
export async function textDigest(value: string) {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(value),
  );
  return Array.from(new Uint8Array(digest), (n) =>
    n.toString(16).padStart(2, "0"),
  ).join("");
}
export function coachSourceKey(row: Opportunity) {
  return JSON.stringify([
    row.id,
    row.profileVersionId,
    row.profileStatus,
    row.sourceStatus,
    row.sourceEvidenceVersion,
    row.sourceObservedAt,
    row.url,
    row.excerpt,
    row.sample === true,
  ]);
}
export function coachSourceProblem(row: Opportunity) {
  if (row.sample || row.id === "sample")
    return "公开研究样例只读，不能调用客户短句服务。";
  if (row.profileStatus !== "CONFIRMED" || !row.profileVersionId)
    return "画像版本尚未确认，请先核对商机画像。";
  if (
    row.sourceStatus !== "OPEN" ||
    !row.sourceEvidenceVersion ||
    !row.sourceObservedAt ||
    !row.excerpt.trim()
  )
    return "来源或证据版本尚未核验，请刷新原文后再生成短句建议。";
  if (
    !id.safeParse(row.profileVersionId).success ||
    !id.safeParse(row.sourceEvidenceVersion).success ||
    !instant.safeParse(row.sourceObservedAt).success ||
    !url.safeParse(row.url).success ||
    !body.safeParse(row.excerpt).success
  )
    return "来源证据格式无效，请重新核验。";
  return "";
}
export async function makeCoachInput(
  row: Opportunity,
  draft: ContactDraft,
  purpose: CoachPurpose,
  requestId: string,
  accountScope: CoachAccountScope,
): Promise<CoachInput> {
  const problem = coachSourceProblem(row);
  if (problem) throw new Error(problem);
  if (
    draft.opportunityId !== row.id ||
    draft.content.length > 8000 ||
    draft.content.includes("\0")
  )
    throw new Error("草稿与商机不一致或内容超出限制。");
  const binding = coachBindingSchema.parse({
    accountScope,
    requestId,
    opportunityId: row.id,
    profileVersionId: row.profileVersionId,
    sourceEvidenceVersion: row.sourceEvidenceVersion,
    sourceUrl: row.url,
    sourceObservedAt: row.sourceObservedAt,
    channel: draft.channel,
    draftVersion: draft.version,
    draftHash: await textDigest(draft.content),
    purpose,
  });
  return { binding, content: draft.content, sourceText: row.excerpt };
}
export function readCoachSuggestion(
  value: unknown,
  input: CoachInput,
  now = Date.now(),
) {
  const data = coachSuggestionSchema.parse(value);
  if (
    JSON.stringify(data.binding) !==
    JSON.stringify(coachBindingSchema.parse(input.binding))
  )
    throw new Error("短句建议与本次草稿、来源或请求不匹配，当前内容已保留。");
  if (
    Date.parse(data.expiresAt) <= now ||
    Date.parse(data.createdAt) > now + 60_000 ||
    Date.parse(data.expiresAt) <= Date.parse(data.createdAt)
  )
    throw new Error("短句建议已过期或时间无效，请重新生成。");
  const quoteIds = new Set(data.quotes.map((quote) => quote.id));
  if (
    quoteIds.size !== data.quotes.length ||
    data.quotes.some(
      (quote) =>
        quote.sourceUrl !== input.binding.sourceUrl ||
        quote.sourceEvidenceVersion !== input.binding.sourceEvidenceVersion ||
        quote.end > input.sourceText.length ||
        input.sourceText.slice(quote.start, quote.end) !== quote.text,
    )
  )
    throw new Error("建议引用与当前原文版本不一致，不能应用。");
  if (
    [
      ...data.context.quoteIds,
      ...data.checks.flatMap((check) => check.quoteIds),
    ].some((quoteId) => !quoteIds.has(quoteId))
  )
    throw new Error("建议依据缺少对应原文引用，不能应用。");
  if (
    data.checks.some(
      (check) =>
        ["CONTEXT", "PROMISE"].includes(check.kind) &&
        check.status === "SUPPORTED" &&
        !check.quoteIds.length,
    )
  )
    throw new Error("上下文或承诺检查缺少原文依据，不能标记为有依据。");
  if (!data.content.includes(data.question))
    throw new Error("建议问题与完整短句不一致，不能应用。");
  return data;
}

export const draftSaveBindingSchema = z
  .object({
    opportunityId: id,
    channel: z.enum(["comment", "dm"]),
    requestId: id,
    contentHash: hash,
  })
  .strict();
export type DraftSaveBinding = z.infer<typeof draftSaveBindingSchema>;
const contactDraftSchema = z
  .object({
    opportunityId: id,
    channel: z.enum(["comment", "dm"]),
    content: body,
    savedContent: z.string().max(8000),
    version: z.number().int().min(1),
    accountId: z.string().max(512),
    recipient: z.string().max(512),
    confirmedFingerprint: z.string().optional(),
  })
  .strict();
export const draftSnapshotSchema = z
  .object({
    draft: contactDraftSchema,
    accountScope: accountScopeSchema.nullable(),
    profileVersionId: z.string().max(128),
    sourceEvidenceVersion: z.string().max(128).nullable(),
  })
  .strict();
export type DraftSnapshot = z.infer<typeof draftSnapshotSchema>;
export interface DraftSaveInput {
  binding: DraftSaveBinding;
  snapshot: DraftSnapshot;
}
export const draftSaveReceiptSchema = z
  .object({
    binding: draftSaveBindingSchema,
    status: z.enum(["SUCCEEDED", "FAILED", "PENDING", "UNKNOWN"]),
    confirmed: z.boolean(),
    snapshot: draftSnapshotSchema.optional(),
  })
  .strict();
export type DraftSaveReceipt = z.infer<typeof draftSaveReceiptSchema>;
export function draftSaveKey(binding: DraftSaveBinding) {
  const b = draftSaveBindingSchema.parse(binding);
  return JSON.stringify([
    b.opportunityId,
    b.channel,
    b.requestId,
    b.contentHash,
  ]);
}
export function draftSaveBindingFromKey(key: string) {
  const parsed: unknown = JSON.parse(key);
  if (!Array.isArray(parsed) || parsed.length !== 4)
    throw new Error("草稿保存记录无效，请先核对原操作。");
  return draftSaveBindingSchema.parse({
    opportunityId: parsed[0],
    channel: parsed[1],
    requestId: parsed[2],
    contentHash: parsed[3],
  });
}
export function draftSnapshot(
  row: Opportunity,
  draft: ContactDraft,
  accountScope?: CoachAccountScope,
): DraftSnapshot {
  return draftSnapshotSchema.parse({
    draft: { ...draft, confirmedFingerprint: undefined },
    accountScope: accountScope || null,
    profileVersionId: row.profileVersionId,
    sourceEvidenceVersion: row.sourceEvidenceVersion || null,
  });
}
export function snapshotDigest(snapshot: DraftSnapshot) {
  const { draft, accountScope, profileVersionId, sourceEvidenceVersion } =
    draftSnapshotSchema.parse(snapshot);
  return textDigest(
    JSON.stringify([
      draft.opportunityId,
      draft.channel,
      draft.version,
      draft.content,
      draft.accountId,
      draft.recipient,
      profileVersionId,
      sourceEvidenceVersion,
      accountScope,
    ]),
  );
}
export async function readDraftSaveReceipt(
  value: unknown,
  binding: DraftSaveBinding,
) {
  const receipt = draftSaveReceiptSchema.parse(value);
  if (draftSaveKey(receipt.binding) !== draftSaveKey(binding))
    throw new Error("保存回执与原请求不匹配，保护继续保留。");
  if (["SUCCEEDED", "FAILED"].includes(receipt.status) && !receipt.confirmed)
    throw new Error("保存终态尚未确认，保护继续保留。");
  if (
    receipt.status === "SUCCEEDED" &&
    (!receipt.snapshot ||
      receipt.snapshot.draft.savedContent !== receipt.snapshot.draft.content ||
      (await snapshotDigest(receipt.snapshot)) !== binding.contentHash)
  )
    throw new Error("已保存内容与原提交快照不一致，保护继续保留。");
  return receipt;
}
