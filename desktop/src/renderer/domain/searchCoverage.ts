import { z } from "zod";
import { explicitInstant } from "./opportunityLibrary";
import {searchCoverageQuerySchema} from '../../shared/searchCoverage';
export {searchCoverageQuerySchema} from '../../shared/searchCoverage';

const id = z
  .string()
  .trim()
  .min(1)
  .max(128)
  .refine((value) => !/[\u0000-\u001f\u007f]/.test(value));
const text = z.string().trim().min(1).max(4000);
const revision = z.number().int().positive().max(Number.MAX_SAFE_INTEGER);
const count = z
  .number()
  .int()
  .nonnegative()
  .max(Number.MAX_SAFE_INTEGER)
  .nullable();
const instant = z.string().refine(explicitInstant);
const platform = z.enum(["xhs", "douyin", "bilibili", "zhihu", "web"]);
export const coverageState = z.enum([
  "NOT_STARTED",
  "RUNNING",
  "PARTIAL",
  "COMPLETE",
]);
export const screeningState = z.enum([
  "HAS_CANDIDATES",
  "PENDING_REVIEW",
  "ALL_EXCLUDED",
  "NO_QUALIFIED",
  "MIXED",
  "UNKNOWN",
]);
const stopReason = z.enum([
  "NONE",
  "ACCESS_FAILED",
  "NOT_EXECUTED",
  "LOGIN_EXPIRED",
  "RATE_LIMITED",
  "DEVICE_OFFLINE",
  "LIMIT_REACHED",
  "CANCELED",
  "UNKNOWN",
]);
const windowSchema = z
  .object({
    id,
    start: instant,
    end: instant,
    timezone: z
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
      }),
  })
  .strict();
const evidence = z
  .object({
    id,
    sourceId: id,
    sourceVersionId: id,
    excerpt: text,
    url: z
      .string()
      .max(2048)
      .refine((value) => {
        try {
          const url = new URL(value);
          return (
            ["https:", "http:"].includes(url.protocol) &&
            !url.username &&
            !url.password
          );
        } catch {
          return false;
        }
      }),
  })
  .strict();
const counters = z
  .object({
    requests: count,
    rawContents: count,
    duplicates: count,
    independentSources: count,
    newCandidates: count,
    confirmedOpportunities: count,
    pendingReviews: count,
  })
  .strict();
const exclusion = z
  .object({
    id,
    phase: z.enum(["DEDUPLICATION", "FILTERING"]),
    reason: text,
    count,
    ruleVersion: id,
    overlapping: z.boolean(),
    evidence: z.array(evidence).max(1000),
  })
  .strict();
const unitSchema = z
  .object({
    id,
    platform,
    direction: z.string().trim().min(1).max(300),
    scope: text,
    coverage: coverageState,
    screening: screeningState,
    stopReason,
    explanation: text,
    unchecked: z.array(text).max(100),
    counts: counters,
    countingBasis: text,
    exclusions: z.array(exclusion).max(100),
    evidence: z.array(evidence).max(1000),
    recovery: z.enum(["NONE", "RESUMABLE_CONFIRMED", "TERMINAL", "UNKNOWN"]),
  })
  .strict();
const usageSchema = z
  .object({
    unit: z.literal("SOUBEI"),
    ruleVersion: id,
    budgetRevision: revision,
    estimated: count,
    maximum: count,
    actual: count,
    settlement: z.enum([
      "NOT_STARTED",
      "RESERVED",
      "PENDING",
      "SETTLED",
      "UNKNOWN",
    ]),
  })
  .strict();
const snapshotSchema = z
  .object({
    contractVersion: z.literal(1),
    requestId: id,
    snapshotId: id,
    audience: z.literal("CUSTOMER"),
    userId: id,
    accountScopeId: id,
    scopeVersion: revision,
    taskId: id,
    runId: id,
    profileId: id,
    profileVersion: revision,
    configurationRevision: revision,
    window: windowSchema,
    generatedAt: instant,
    expiresAt: instant,
    deduplicationVersion: id,
    coverage: coverageState,
    screening: screeningState,
    units: z.array(unitSchema).max(100),
    usage: usageSchema.nullable(),
  })
  .strict();
export type SearchCoverageQuery = z.infer<typeof searchCoverageQuerySchema>;
export type CoverageSnapshot = z.infer<typeof snapshotSchema>;
export type CoverageUnit = z.infer<typeof unitSchema>;
export type CoverageEvidence = z.infer<typeof evidence>;
export type CoveragePlanRequest = {
  kind: "ADJUST_LIMIT" | "NEW_DRAFT";
  snapshotId: string;
  taskId: string;
  runId: string;
  unitId: string;
  profileId: string;
  profileVersion: number;
  configurationRevision: number;
  windowId: string;
  accountScopeId: string;
  scopeVersion: number;
  userId: string;
  expiresAt: string;
  deduplicationVersion: string;
  budgetRevision: number | null;
};
const reserved = (value: string) =>
  value === "sample" || value.startsWith("sample:");
const distinct = (values: { id: string }[]) =>
  new Set(values.map((value) => value.id)).size === values.length;

/** The service resolves the active account. Expected scope is a consistency guard,
 * never authorization. Nested units/evidence inherit this exact immutable window. */
export function parseCoverageSnapshot(
  value: unknown,
  expected: SearchCoverageQuery,
  now = Date.now(),
): CoverageSnapshot {
  const query = searchCoverageQuerySchema.parse(expected);
  const parsed = snapshotSchema.safeParse(value);
  if (!parsed.success)
    throw new Error("覆盖数据不完整或版本不受支持，请刷新重试。");
  const result = parsed.data;
  if (
    result.requestId !== query.requestId ||
    result.taskId !== query.taskId ||
    result.profileId !== query.profileId ||
    result.profileVersion !== query.profileVersion ||
    result.userId !== query.expectedScope.userId ||
    result.accountScopeId !== query.expectedScope.accountScopeId ||
    result.scopeVersion !== query.expectedScope.scopeVersion ||
    [result.taskId, result.runId, result.profileId, result.snapshotId].some(
      reserved,
    )
  )
    throw new Error("覆盖数据与当前账户、任务或画像版本不一致，请重新读取。");
  if (
    Date.parse(result.window.start) >= Date.parse(result.window.end) ||
    Date.parse(result.generatedAt) > now ||
    Date.parse(result.generatedAt) >= Date.parse(result.expiresAt) ||
    !distinct(result.units)
  )
    throw new Error("覆盖窗口、时效或方向标识无效，请刷新重试。");
  if (
    (result.coverage === "COMPLETE" &&
      (!result.units.length ||
        result.units.some((unit) => unit.coverage !== "COMPLETE"))) ||
    (result.coverage === "PARTIAL" &&
      (!result.units.length ||
        result.units.every((unit) => unit.coverage === "COMPLETE"))) ||
    (result.coverage === "NOT_STARTED" &&
      result.units.some((unit) => unit.coverage !== "NOT_STARTED"))
  )
    throw new Error("覆盖完整度与方向明细不一致，不能判断本轮结果。");
  for (const unit of result.units) {
    const terminalScreening = ["ALL_EXCLUDED", "NO_QUALIFIED"].includes(
      unit.screening,
    );
    if (
      (terminalScreening &&
        (unit.coverage !== "COMPLETE" || unit.counts.pendingReviews !== 0)) ||
      (unit.screening === "ALL_EXCLUDED" &&
        !(
          unit.counts.independentSources !== null &&
          unit.counts.independentSources > 0 &&
          unit.exclusions.some(
            (row) =>
              row.phase === "FILTERING" && row.count !== null && row.count > 0,
          )
        )) ||
      (unit.coverage === "COMPLETE" && unit.unchecked.length > 0) ||
      (unit.coverage === "COMPLETE" &&
        [
          "ACCESS_FAILED",
          "LOGIN_EXPIRED",
          "NOT_EXECUTED",
          "DEVICE_OFFLINE",
          "RATE_LIMITED",
          "UNKNOWN",
        ].includes(unit.stopReason)) ||
      (unit.coverage !== "COMPLETE" && unit.unchecked.length === 0) ||
      (unit.recovery === "RESUMABLE_CONFIRMED" &&
        unit.stopReason !== "LIMIT_REACHED") ||
      !distinct(unit.exclusions) ||
      !distinct(unit.evidence) ||
      unit.exclusions.some(
        (row) =>
          !distinct(row.evidence) ||
          (row.count !== null && row.count > 0 && !row.evidence.length),
      )
    )
      throw new Error("覆盖结论缺少已完成范围、复核或排除依据，请重新读取。");
    const sources = [
      ...unit.evidence,
      ...unit.exclusions.flatMap((row) => row.evidence),
    ];
    if (
      sources.some((source) =>
        [source.id, source.sourceId, source.sourceVersionId].some(reserved),
      )
    )
      throw new Error("公开样例不能作为客户覆盖统计依据。");
  }
  if (
    ["ALL_EXCLUDED", "NO_QUALIFIED"].includes(result.screening) &&
    (result.coverage !== "COMPLETE" ||
      result.units.some((unit) => unit.screening !== result.screening))
  )
    throw new Error("不能把部分范围或待复核内容概括为无合格机会。");
  if (
    result.usage &&
    ((result.usage.maximum !== null &&
      result.usage.actual !== null &&
      result.usage.actual > result.usage.maximum) ||
      (result.usage.settlement === "SETTLED" && result.usage.actual === null))
  )
    throw new Error("搜贝用量与已授权上限或结算状态不一致，请核对原记录。");
  return result;
}

export const coverageLabels: Record<CoverageSnapshot["coverage"], string> = {
  NOT_STARTED: "未开始",
  RUNNING: "检查中",
  PARTIAL: "部分完成",
  COMPLETE: "已完成",
};
export const screeningLabels: Record<CoverageSnapshot["screening"], string> = {
  HAS_CANDIDATES: "有候选",
  PENDING_REVIEW: "待复核",
  ALL_EXCLUDED: "内容均被排除",
  NO_QUALIFIED: "已检查范围无合格机会",
  MIXED: "各方向结果不同",
  UNKNOWN: "尚不能判断",
};
export function coverageResultLabel(unit: CoverageUnit) {
  if (["ACCESS_FAILED", "LOGIN_EXPIRED"].includes(unit.stopReason))
    return "访问失败";
  if (unit.stopReason === "LIMIT_REACHED") return "研究用量已达上限";
  if (unit.stopReason === "NOT_EXECUTED") return "尚未执行";
  if (unit.stopReason === "RATE_LIMITED") return "访问受限";
  if (unit.stopReason === "DEVICE_OFFLINE") return "设备离线";
  return screeningLabels[unit.screening];
}
export function coveragePlan(
  snapshot: CoverageSnapshot,
  unit: CoverageUnit,
): CoveragePlanRequest | null {
  if (
    unit.stopReason !== "LIMIT_REACHED" ||
    !["RESUMABLE_CONFIRMED", "TERMINAL"].includes(unit.recovery)
  )
    return null;
  if (unit.recovery === "RESUMABLE_CONFIRMED" && !snapshot.usage) return null;
  return {
    kind:
      unit.recovery === "RESUMABLE_CONFIRMED" ? "ADJUST_LIMIT" : "NEW_DRAFT",
    snapshotId: snapshot.snapshotId,
    taskId: snapshot.taskId,
    runId: snapshot.runId,
    unitId: unit.id,
    profileId: snapshot.profileId,
    profileVersion: snapshot.profileVersion,
    configurationRevision: snapshot.configurationRevision,
    windowId: snapshot.window.id,
    accountScopeId: snapshot.accountScopeId,
    scopeVersion: snapshot.scopeVersion,
    userId: snapshot.userId,
    expiresAt: snapshot.expiresAt,
    deduplicationVersion: snapshot.deduplicationVersion,
    budgetRevision: snapshot.usage?.budgetRevision ?? null,
  };
}
