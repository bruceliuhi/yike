import { z } from "zod";
import type { TaskAction, TaskDraft, TaskRun } from "./models";
import { taskFingerprint } from "./task";
import { usageReservationSchema, type UsageReservation } from "./researchUsage";
import { scheduleSchema } from "./schedule";

const id = z.string().regex(/^[A-Za-z0-9_-][A-Za-z0-9_.:-]{0,127}$/);
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const revision = z.number().int().positive().max(Number.MAX_SAFE_INTEGER);
const mode = z.enum(["once", "monitor"]);
const platform = z.enum(["xhs", "douyin", "bilibili", "zhihu", "web"]);
const date = z.string().datetime({ offset: true });
const count = z.number().int().nonnegative().max(Number.MAX_SAFE_INTEGER);
export const TASK_STATES = [
  "PENDING",
  "RUNNING",
  "PAUSED",
  "COMPLETED",
  "FAILED",
  "CANCELED",
  "BLOCKED",
  "PARTIAL",
  "OFFLINE",
  "RETRYING",
  "CANCELLING",
  "PAUSING",
  "RESUMING",
] as const;
export const taskRunSchema = z.object({
  id,
  name: z.string().trim().min(1).max(200),
  mode,
  status: z.string().min(1).max(80),
  platforms: z
    .array(platform)
    .max(5)
    .refine((p) => new Set(p).size === p.length),
  updatedAt: date.optional(),
  createdAt: date.optional(),
  lastRunAt: date.optional(),
  nextRunAt: date.optional(),
  profileId: id.optional(),
  profileVersion: revision.optional(),
  profileName: z.string().max(200).optional(),
  keywords: z.array(z.string().max(80)).max(20).optional(),
  regions: z.string().max(1000).optional(),
  failureReason: z.string().max(8000).optional(),
  schedule: scheduleSchema.optional(),
  platformStages: z
    .array(
      z.object({
        platform,
        status: z.string(),
        phase: z.string().optional(),
        reason: z.string().optional(),
        accountName: z.string().optional(),
        newCount: count.optional(),
        updatedAt: date.optional(),
        nextRetryAt: date.optional(),
      }),
    )
    .max(5)
    .optional(),
  events: z
    .array(
      z.object({
        id: z.string(),
        message: z.string(),
        occurredAt: date.optional(),
        platform: platform.optional(),
        level: z.enum(["info", "warning", "error"]).optional(),
      }),
    )
    .optional(),
  statistics: z
    .object({
      today: count.optional(),
      week: count.optional(),
      month: count.optional(),
      total: count.optional(),
    })
    .optional(),
});
export function parseTaskRuns(value: unknown): TaskRun[] {
  const rows = z.array(taskRunSchema).parse(value);
  if (new Set(rows.map((row) => row.id)).size !== rows.length)
    throw new Error("任务列表包含重复编号，请刷新重试。");
  return rows;
}
export function matchesCreatedTask(
  value: unknown,
  draft: TaskDraft,
): value is TaskRun {
  const parsed = taskRunSchema.safeParse(value);
  if (!parsed.success) return false;
  const run = parsed.data;
  return (
    run.mode === draft.mode &&
    run.name === draft.name.trim() &&
    (TASK_STATES as readonly string[]).includes(run.status) &&
    run.platforms.length === draft.platforms.length &&
    run.platforms.every((p) => draft.platforms.includes(p)) &&
    (run.profileId === undefined || run.profileId === draft.profileId) &&
    (run.profileVersion === undefined ||
      run.profileVersion === draft.profileVersion)
  );
}
export async function configurationHash(draft: TaskDraft): Promise<string> {
  return hashText(taskFingerprint(draft));
}
export async function hashText(value: string) {
  return [
    ...new Uint8Array(
      await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)),
    ),
  ]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}
export interface TaskStartBinding {
  usageReservation?: UsageReservation;
  requestId: string;
  draftId: string;
  revision: number;
  configurationHash: string;
  mode: "once" | "monitor";
}
export type TaskStartLookup = Omit<
  TaskStartBinding,
  "configurationHash" | "mode"
> &
  Partial<Pick<TaskStartBinding, "configurationHash" | "mode">>;
export function startEntry(binding: TaskStartBinding) {
  return JSON.stringify([
    binding.requestId,
    binding.revision,
    binding.configurationHash,
    binding.mode,
    ...(binding.usageReservation ? [binding.usageReservation] : []),
  ]);
}
export function readStartEntry(
  draftId: string,
  entry: string,
): TaskStartLookup | undefined {
  try {
    const [requestId, rev, digest, kind, usageReservation] = z
      .tuple([z.string(), revision, hash, mode]).rest(usageReservationSchema)
      .parse(JSON.parse(entry));
    if (JSON.parse(entry).length > 5) return;
    if (requestId !== `task:${draftId}:${rev}`) return;
    return {
      draftId,
      requestId,
      revision: rev,
      configurationHash: digest,
      mode: kind,
      ...(usageReservation ? { usageReservation } : {}),
    };
  } catch {
    const prefix = `task:${draftId}:`;
    if (!entry.startsWith(prefix) || !/^\d+$/.test(entry.slice(prefix.length)))
      return;
    const rev = Number(entry.slice(prefix.length));
    if (!Number.isSafeInteger(rev) || rev < 1) return;
    return { draftId, requestId: entry, revision: rev };
  }
}
const startFields = {
  usageReservation: usageReservationSchema.optional(),
  requestId: z.string().min(1).max(700),
  draftId: z.string().min(1).max(512),
  revision,
  configurationHash: hash,
  mode,
};
const startReceipt = z.discriminatedUnion("status", [
  z.object({
    ...startFields,
    status: z.literal("ACCEPTED"),
    run: taskRunSchema,
  }),
  z.object({
    ...startFields,
    status: z.literal("REJECTED"),
    confirmedNotStarted: z.literal(true),
    confirmedNoUsageReserved: z.literal(true).optional(),
    message: z.string().max(2000).optional(),
  }),
  z.object({
    ...startFields,
    status: z.enum(["PENDING", "UNKNOWN"]),
    message: z.string().max(2000).optional(),
  }),
]);
export type TaskStartReceipt = z.infer<typeof startReceipt>;
export function parseStartReceipt(
  value: unknown,
  expected: TaskStartLookup,
): TaskStartReceipt {
  const parsed = startReceipt.safeParse(value);
  if (!parsed.success)
    throw new Error("原请求缺少可核验的启动回执，保护继续保留。");
  const receipt = parsed.data;
  if (
    receipt.requestId !== expected.requestId ||
    receipt.draftId !== expected.draftId ||
    receipt.revision !== expected.revision ||
    (expected.configurationHash &&
      receipt.configurationHash !== expected.configurationHash) ||
    (expected.mode && receipt.mode !== expected.mode)
  )
    throw new Error("启动回执与原请求或确认配置不匹配，保护继续保留。");
  if (expected.usageReservation && (receipt.status === "ACCEPTED" || receipt.status === "REJECTED") &&
      (!receipt.usageReservation || Object.entries(expected.usageReservation).some(([key, value]) => receipt.usageReservation![key as keyof UsageReservation] !== value)))
    throw new Error("启动回执尚未确认原搜贝上限与计量规则，保护继续保留。");
  if (expected.usageReservation && receipt.status === "REJECTED" && receipt.confirmedNoUsageReserved !== true)
    throw new Error("原请求的搜贝预留尚未核对，保护继续保留。");
  if (!expected.configurationHash || !expected.mode)
    throw new Error(
      "旧请求未保存确认配置摘要，请联系服务方核对原请求；当前不会重复启动。",
    );
  if (
    receipt.status === "ACCEPTED" &&
    (receipt.run.mode !== expected.mode ||
      !(TASK_STATES as readonly string[]).includes(receipt.run.status))
  )
    throw new Error("返回任务与确认配置不匹配，保护继续保留。");
  return receipt;
}

export const taskActionsFor = (status: string): TaskAction[] => {
  if (["RUNNING", "RETRYING"].includes(status)) return ["pause", "cancel"];
  if (status === "PAUSED") return ["resume", "cancel"];
  if (status === "FAILED") return ["retry"];
  if (["PARTIAL", "BLOCKED"].includes(status)) return ["retry", "cancel"];
  if (["PENDING", "OFFLINE"].includes(status)) return ["cancel"];
  return [];
};
export function taskActionFingerprint(run: TaskRun) {
  return JSON.stringify([
    run.id,
    run.mode,
    run.status,
    run.updatedAt ?? null,
    run.profileId ?? null,
    run.profileVersion ?? null,
    run.platforms,
  ]);
}
export interface TaskActionBinding {
  requestId: string;
  taskId: string;
  action: TaskAction;
  expectedHash: string;
}
export const actionEntry = (binding: TaskActionBinding) =>
  JSON.stringify([
    binding.taskId,
    binding.action,
    binding.expectedHash,
    binding.requestId,
  ]);
export function readActionEntry(key: string): TaskActionBinding | undefined {
  try {
    const [taskId, action, expectedHash, requestId] = z
      .tuple([
        id,
        z.enum(["pause", "resume", "retry", "cancel"]),
        hash,
        z.string().min(1).max(128),
      ])
      .parse(JSON.parse(key));
    return { taskId, action, expectedHash, requestId };
  } catch {
    return;
  }
}
const actionFields = {
  requestId: z.string().min(1).max(128),
  taskId: id,
  action: z.enum(["pause", "resume", "retry", "cancel"]),
  expectedHash: hash,
};
const actionReceipt = z.discriminatedUnion("status", [
  z.object({
    ...actionFields,
    status: z.literal("APPLIED"),
    run: taskRunSchema,
  }),
  z.object({
    ...actionFields,
    status: z.literal("REJECTED"),
    confirmedNotApplied: z.literal(true),
    message: z.string().max(2000).optional(),
  }),
  z.object({
    ...actionFields,
    status: z.enum(["PENDING", "UNKNOWN"]),
    message: z.string().max(2000).optional(),
  }),
]);
export type TaskActionReceipt = z.infer<typeof actionReceipt>;
export function parseActionReceipt(
  value: unknown,
  expected: TaskActionBinding,
): TaskActionReceipt {
  const parsed = actionReceipt.safeParse(value);
  if (!parsed.success)
    throw new Error("操作回执缺少原请求或确定状态，保护继续保留。");
  const result = parsed.data;
  if (
    result.requestId !== expected.requestId ||
    result.taskId !== expected.taskId ||
    result.action !== expected.action ||
    result.expectedHash !== expected.expectedHash
  )
    throw new Error("任务操作回执与原请求不匹配，保护继续保留。");
  const targets: Record<TaskAction, string[]> = {
    pause: ["PAUSED"],
    resume: ["PENDING", "RUNNING", "RETRYING"],
    retry: ["PENDING", "RUNNING", "RETRYING"],
    cancel: ["CANCELED"],
  };
  if (
    result.status === "APPLIED" &&
    (result.run.id !== expected.taskId ||
      !targets[expected.action].includes(result.run.status))
  )
    throw new Error("任务状态尚未证实本次操作完成，保护继续保留。");
  return result;
}
