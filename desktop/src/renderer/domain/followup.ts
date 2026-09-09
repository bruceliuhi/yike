import { z } from "zod";
import type { Followup } from "./models";
export const FOLLOWUP_LABELS = {
  CONTACTED: "已联系",
  REPLIED: "已回复",
  MEETING: "已约谈",
  QUOTED: "已报价",
  LOST: "未成交",
  WON: "已成交",
} as const;
const id = z.string().min(1).max(512);
const time = z
  .string()
  .refine((v) => Number.isFinite(Date.parse(v)), "时间无效");
export const followupFieldsSchema = z.object({
  status: z.enum(["CONTACTED", "REPLIED", "MEETING", "QUOTED", "LOST", "WON"]),
  note: z.string().trim().min(1).max(500),
  occurredAt: time.nullable(),
  nextStep: z.string().max(500),
  nextFollowupAt: time.nullable(),
  ownerId: id,
});
export type FollowupFields = z.infer<typeof followupFieldsSchema>;
export const followupRecordSchema = followupFieldsSchema.extend({
  id,
  opportunityId: id,
  profileVersionId: id,
  revision: z.number().int().positive(),
  title: z.string(),
  createdAt: time,
  kind: z.literal("manual"),
  ownerName: z.string(),
  state: z.enum(["ACTIVE", "CORRECTED", "VOID"]),
  sample: z.boolean(),
  correctsId: id.optional(),
  reason: z.string().optional(),
  replyCount: z.number().int().nonnegative().optional(),
});
export type FollowupRecord = z.infer<typeof followupRecordSchema>;
export type FollowupView = Omit<
  FollowupRecord,
  "profileVersionId" | "revision" | "occurredAt" | "ownerId"
> & {
  profileVersionId: string;
  revision: number;
  occurredAt: string | null;
  ownerId: string;
  legacy?: boolean;
};
export const replySchema = z.object({
  id,
  revision: z.number().int().positive(),
  opportunityId: id.nullable(),
  profileVersionId: id.nullable(),
  sendRequestId: id.nullable(),
  platform: z.string().min(1),
  content: z.string(),
  receivedAt: time,
  read: z.boolean(),
  sample: z.boolean(),
  unmatchedReason: z.string().optional(),
});
export type LinkedReply = z.infer<typeof replySchema>;
export const snapshotSchema = z.object({
  records: z.array(followupRecordSchema),
  members: z.array(z.object({ id, name: z.string().min(1) })),
});
export type FollowupSnapshot = z.infer<typeof snapshotSchema>;
function uniqueIds(rows: { id: string }[]) {
  if (new Set(rows.map((r) => r.id)).size !== rows.length)
    throw new Error("服务返回重复记录，请刷新核对。");
}
export function readSnapshot(value: unknown) {
  const result = snapshotSchema.safeParse(value);
  if (!result.success) throw new Error("跟进数据格式不完整，请刷新重试。");
  uniqueIds(result.data.records);
  uniqueIds(result.data.members);
  return result.data;
}
export function readReplies(value: unknown, opportunityId?: string) {
  const result = z.array(replySchema).safeParse(value);
  if (!result.success) throw new Error("回复数据格式不完整，请刷新重试。");
  uniqueIds(result.data);
  if (result.data.some((r) => r.opportunityId !== (opportunityId || null)))
    throw new Error("回复与当前商机不匹配，请刷新核对。");
  return result.data;
}
export function legacyRecord(row: Followup): FollowupView {
  return {
    ...row,
    kind: "manual",
    profileVersionId: "",
    revision: 0,
    occurredAt: null,
    nextStep: "",
    nextFollowupAt: null,
    ownerId: "",
    ownerName: "未提供",
    state: "ACTIVE",
    sample: row.opportunityId === "sample",
    legacy: true,
  };
}
export type FollowupAction =
  | "create"
  | "correct"
  | "void"
  | "mark-read"
  | "legacy-create";
export interface FollowupBinding {
  opportunityId: string;
  profileVersionId: string;
  action: FollowupAction;
  targetId: string;
  targetRevision: number;
  requestId: string;
}
export interface FollowupMutation {
  binding: FollowupBinding;
  values?: FollowupFields;
  reason?: string;
}
export interface FollowupReceipt {
  binding: FollowupBinding;
  status: "PENDING" | "UNKNOWN" | "SUCCEEDED" | "FAILED";
  confirmed?: boolean;
  record?: FollowupRecord;
  reply?: LinkedReply;
  message?: string;
}
export function followupKey(b: FollowupBinding) {
  return JSON.stringify([
    b.opportunityId,
    b.profileVersionId,
    b.action,
    b.targetId,
    b.targetRevision,
    b.requestId,
  ]);
}
export function bindingFromKey(key: string): FollowupBinding {
  const [
    opportunityId,
    profileVersionId,
    action,
    targetId,
    targetRevision,
    requestId,
  ] = JSON.parse(key);
  return {
    opportunityId,
    profileVersionId,
    action,
    targetId,
    targetRevision,
    requestId,
  };
}
export function readReceipt(
  value: unknown,
  b: FollowupBinding,
): FollowupReceipt {
  const schema = z.object({
    binding: z.object({
      opportunityId: id,
      profileVersionId: id,
      action: z.enum([
        "create",
        "correct",
        "void",
        "mark-read",
        "legacy-create",
      ]),
      targetId: z.string(),
      targetRevision: z.number().int().nonnegative(),
      requestId: id,
    }),
    status: z.enum(["PENDING", "UNKNOWN", "SUCCEEDED", "FAILED"]),
    confirmed: z.boolean().optional(),
    record: followupRecordSchema.optional(),
    reply: replySchema.optional(),
    message: z.string().optional(),
  });
  const parsed = schema.safeParse(value);
  if (!parsed.success || followupKey(parsed.data.binding) !== followupKey(b))
    throw new Error("回执与原跟进操作不匹配，保护仍保留。");
  const r = parsed.data;
  if (["SUCCEEDED", "FAILED"].includes(r.status) && r.confirmed !== true)
    throw new Error("原操作尚无确定回执，保护仍保留。");
  if (r.status === "SUCCEEDED") {
    if (b.action === "mark-read") {
      if (
        !r.reply ||
        r.reply.id !== b.targetId ||
        r.reply.opportunityId !== b.opportunityId ||
        r.reply.profileVersionId !== b.profileVersionId ||
        r.reply.revision <= b.targetRevision ||
        !r.reply.read ||
        r.reply.sample
      )
        throw new Error("已读回执与原回复不匹配。");
    } else if (
      !r.record ||
      r.record.sample ||
      r.record.opportunityId !== b.opportunityId ||
      r.record.profileVersionId !== b.profileVersionId ||
      (b.action === "create" &&
        (r.record.state !== "ACTIVE" || !!r.record.correctsId)) ||
      (b.action === "correct" &&
        (r.record.correctsId !== b.targetId ||
          r.record.id === b.targetId ||
          r.record.state !== "ACTIVE")) ||
      (b.action === "void" &&
        (r.record.id !== b.targetId ||
          r.record.state !== "VOID" ||
          r.record.revision <= b.targetRevision))
    )
      throw new Error("保存回执与原商机或记录不匹配。");
  }
  return r;
}
export function legacyNote(fields: FollowupFields) {
  const extra = [
    fields.occurredAt && `联系时间：${fields.occurredAt}`,
    fields.nextStep && `下一步：${fields.nextStep}`,
    fields.nextFollowupAt && `下次跟进：${fields.nextFollowupAt}`,
  ].filter(Boolean);
  return (
    fields.note +
    (extra.length
      ? "\n\n【人工登记补充；未设置提醒】\n" + extra.join("\n")
      : "")
  );
}
