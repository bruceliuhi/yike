import { z } from "zod";

export type OutreachQueue = "confirm" | "reply" | "issues";
export const OUTREACH_QUEUE_LABELS: Record<OutreachQueue, string> = {
  confirm: "待确认", reply: "待回复", issues: "需处理",
};
const id = z.string().trim().min(1).max(512);
const channel = z.enum(["comment", "dm"]);
const version = z.number().int().positive();
export const outreachRecordSchema = z.object({
  id, opportunityId: id, channel, version,
  queue: z.enum(["confirm", "reply", "issues"]),
  title: z.string().min(1), recipientLabel: z.string(), content: z.string(),
  updatedAt: z.string().refine((v) => Number.isFinite(Date.parse(v))),
  sample: z.boolean(), message: z.string().optional(),
});
export type OutreachRecord = z.infer<typeof outreachRecordSchema>;
export interface OutreachQueuePage {
  queue: OutreachQueue; items: OutreachRecord[]; total: number;
}
export function parseOutreachQueue(value: unknown, queue: OutreachQueue): OutreachQueuePage {
  const page = z.object({
    queue: z.literal(queue), items: z.array(outreachRecordSchema),
    total: z.number().int().nonnegative(),
  }).parse(value);
  if (page.total !== page.items.length || new Set(page.items.map((r) => r.id)).size !== page.items.length ||
      page.items.some((r) => r.queue !== queue))
    throw new Error("触达队列记录不完整或身份不匹配，请刷新重试。");
  return page;
}
export interface SendRequestBinding {
  requestId: string; opportunityId: string; channel: "comment" | "dm"; version: number;
}
/** SENT/FAILED are authoritative channel outcomes. FAILED must prove no delivery. */
export type SendReceipt = SendRequestBinding & (
  | { status: "SENT"; confirmed: true; message?: string }
  | { status: "FAILED"; confirmed: true; confirmedNotDelivered: true; message?: string }
  | { status: "PENDING" | "UNKNOWN"; message?: string }
);
export function parseSendReceipt(value: unknown, expected: SendRequestBinding): SendReceipt {
  const binding = { requestId: id, opportunityId: id, channel, version, message: z.string().optional() };
  const parsed = z.discriminatedUnion("status", [
    z.object({ ...binding, status: z.literal("SENT"), confirmed: z.literal(true) }),
    z.object({ ...binding, status: z.literal("FAILED"), confirmed: z.literal(true), confirmedNotDelivered: z.literal(true) }),
    z.object({ ...binding, status: z.enum(["PENDING", "UNKNOWN"]) }),
  ]).safeParse(value);
  if (!parsed.success) throw new Error("发送结果缺少可核验的原请求或确定回执，发送保护仍保留。");
  const receipt = parsed.data;
  if (receipt.requestId !== expected.requestId || receipt.opportunityId !== expected.opportunityId ||
      receipt.channel !== expected.channel || receipt.version !== expected.version)
    throw new Error("返回结果与原发送请求不匹配，发送保护仍保留。");
  return receipt;
}
export function pendingSend(entries: Record<string, string>, opportunityId: string, channel: string) {
  for (const [key, value] of Object.entries(entries)) {
    if (value !== "PENDING") continue;
    try {
      const parts: unknown = JSON.parse(key);
      if (Array.isArray(parts) && parts[0] === opportunityId && parts[1] === channel) {
        return { key, binding: parts.length === 4 ? {
          opportunityId, channel: channel as "comment" | "dm", version: parts[2] as number,
          requestId: parts[3] as string,
        } : undefined };
      }
    } catch { /* Validated by the operation ledger; never infer an operation ID. */ }
  }
  return undefined;
}
