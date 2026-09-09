import { z } from "zod";
import { taskDraftSchema } from "../app/taskDraft";
import type { Session, TaskDraft } from "./models";
import { explicitInstant } from "./opportunityLibrary";
import type { CoveragePlanRequest } from "./searchCoverage";
import {
  defaultResearchSettings,
  researchSettingsSchema,
} from "./researchUsage";
import { hashText } from "./taskOperations";
import { coverageProvenanceSchema } from "./coverageProvenance";

const id = z
  .string()
  .trim()
  .min(1)
  .max(128)
  .refine((value) => !/[\u0000-\u001f\u007f]/.test(value));
const revision = z.number().int().positive().max(Number.MAX_SAFE_INTEGER);
const cap = z.number().int().positive().max(1000000);
const instant = z.string().refine(explicitInstant);
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const planSchema = z
  .object({
    kind: z.enum(["ADJUST_LIMIT", "NEW_DRAFT"]),
    snapshotId: id,
    taskId: id,
    runId: id,
    unitId: id,
    profileId: id,
    profileVersion: revision,
    configurationRevision: revision,
    windowId: id,
    accountScopeId: id,
    scopeVersion: revision,
    userId: id,
    expiresAt: instant,
    deduplicationVersion: id,
    budgetRevision: revision.nullable(),
  })
  .strict();
export interface CoveragePreviewRequest {
  requestId: string;
  plan: CoveragePlanRequest;
  newMaxSoubei?: number;
}
const quoteSchema = z
  .object({
    quoteId: id,
    ruleVersion: id,
    authorizationToken: z.string().min(1).max(512),
    accountScopeId: id,
    scopeVersion: revision,
    taskId: id,
    runId: id,
    budgetRevision: revision,
    oldMaxSoubei: cap,
    newMaxSoubei: cap,
    additionalSoubei: cap,
    estimatedAdditionalSoubei: z
      .number()
      .nonnegative()
      .finite()
      .max(1000000)
      .nullable(),
    expiresAt: instant,
  })
  .strict();
const previewSchema = z.discriminatedUnion("kind", [
  z
    .object({
      kind: z.literal("NEW_DRAFT"),
      requestId: id,
      plan: planSchema,
      previewId: id,
      generatedAt: instant,
      expiresAt: instant,
      recovery: z.literal("TERMINAL"),
      scopeSummary: z.string().trim().min(1).max(4000),
      draft: taskDraftSchema,
    })
    .strict(),
  z
    .object({
      kind: z.literal("ADJUST_LIMIT"),
      requestId: id,
      plan: planSchema,
      previewId: id,
      generatedAt: instant,
      expiresAt: instant,
      recovery: z.literal("RESUMABLE_CONFIRMED"),
      scopeSummary: z.string().trim().min(1).max(4000),
      quote: quoteSchema,
    })
    .strict(),
]);
export type CoveragePlanPreview = z.infer<typeof previewSchema>;
export function coveragePlanCurrent(
  plan: CoveragePlanRequest,
  session: Session,
  now = Date.now(),
) {
  return (
    session.authenticated &&
    !!session.userId &&
    plan.userId === session.userId &&
    plan.accountScopeId === session.accountScope?.id &&
    plan.scopeVersion === session.accountScope.version &&
    explicitInstant(plan.expiresAt) &&
    Date.parse(plan.expiresAt) > now
  );
}
export function readCoveragePreview(
  value: unknown,
  expected: CoveragePreviewRequest,
  session: Session,
  now = Date.now(),
): CoveragePlanPreview {
  const plan = planSchema.parse(expected.plan);
  const result = previewSchema.parse(value);
  if (
    !coveragePlanCurrent(plan, session, now) ||
    result.requestId !== expected.requestId ||
    result.kind !== plan.kind ||
    JSON.stringify(result.plan) !== JSON.stringify(plan)
  )
    throw new Error("补查预览与原任务、范围或客户空间不一致，请重新读取。");
  if (
    Date.parse(result.generatedAt) > now ||
    Date.parse(result.generatedAt) >= Date.parse(result.expiresAt) ||
    Date.parse(result.expiresAt) <= now ||
    Date.parse(result.expiresAt) > Date.parse(plan.expiresAt)
  )
    throw new Error("补查预览已过期或时效无效，请重新读取。");
  if (result.kind === "NEW_DRAFT") {
    if (
      result.draft.profileId !== plan.profileId ||
      result.draft.profileVersion !== plan.profileVersion ||
      result.draft.revision !== plan.configurationRevision ||
      !result.draft.name.trim()
    )
      throw new Error("补查条件缺少原画像或配置版本，请重新读取。");
    if (result.draft.research)
      researchSettingsSchema.parse(result.draft.research);
  } else {
    const quote = result.quote;
    if (
      quote.accountScopeId !== plan.accountScopeId ||
      quote.scopeVersion !== plan.scopeVersion ||
      quote.taskId !== plan.taskId ||
      quote.runId !== plan.runId ||
      quote.budgetRevision !== plan.budgetRevision ||
      quote.newMaxSoubei !== expected.newMaxSoubei ||
      quote.newMaxSoubei <= quote.oldMaxSoubei ||
      quote.additionalSoubei !== quote.newMaxSoubei - quote.oldMaxSoubei ||
      (quote.estimatedAdditionalSoubei !== null &&
        quote.estimatedAdditionalSoubei > quote.additionalSoubei) ||
      Date.parse(quote.expiresAt) <= now ||
      Date.parse(quote.expiresAt) > Date.parse(result.expiresAt)
    )
      throw new Error(
        "搜贝调整估算与旧预算版本、新上限或差额不一致，请重新估算。",
      );
  }
  return result;
}
export function draftFromCoverage(
  preview: Extract<CoveragePlanPreview, { kind: "NEW_DRAFT" }>,
): TaskDraft {
  const original = structuredClone(preview.draft);
  return {
    ...original,
    id: crypto.randomUUID(),
    revision: 1,
    name: (original.name + " · 补查").slice(0, 200),
    savedAt: new Date().toISOString(),
    research: {
      ...(original.research || defaultResearchSettings()),
      coverageProvenance: coverageProvenanceSchema.parse({
        ...preview.plan,
        scopeSummary: preview.scopeSummary,
      }),
    },
  };
}
const adjustmentBinding = z
  .object({
    accountScopeId: id,
    scopeVersion: revision,
    taskId: id,
    requestId: id,
    confirmationHash: hash,
  })
  .strict();
export type CoverageAdjustmentBinding = z.infer<typeof adjustmentBinding>;
export const coverageAdjustmentKey = (binding: CoverageAdjustmentBinding) => {
  const b = adjustmentBinding.parse(binding);
  return JSON.stringify([
    b.accountScopeId,
    b.scopeVersion,
    b.taskId,
    b.requestId,
    b.confirmationHash,
  ]);
};
export function readCoverageAdjustmentKey(key: string) {
  const [accountScopeId, scopeVersion, taskId, requestId, confirmationHash] = z
    .tuple([id, revision, id, id, hash])
    .parse(JSON.parse(key));
  return { accountScopeId, scopeVersion, taskId, requestId, confirmationHash };
}
export function validCoverageAdjustmentEntry(
  key: string,
  value: string,
): boolean {
  try {
    readCoverageAdjustmentKey(key);
    return value === "PENDING";
  } catch {
    return false;
  }
}
export function coverageConfirmationHash(preview: CoveragePlanPreview) {
  // Omit the opaque authorization token from persistent identity material.
  const value =
    preview.kind === "ADJUST_LIMIT"
      ? {
          ...preview,
          quote: { ...preview.quote, authorizationToken: undefined },
        }
      : preview;
  return hashText(JSON.stringify(value));
}
const confirmationSchema = previewSchema.options[1].extend({
  quote: quoteSchema.omit({ authorizationToken: true }),
});
const receiptSchema = z.discriminatedUnion("status", [
  z
    .object({
      binding: adjustmentBinding,
      status: z.literal("APPLIED"),
      notResumed: z.literal(true),
      confirmation: confirmationSchema,
      previousBudgetRevision: revision,
      budgetRevision: revision,
      maximum: cap,
    })
    .strict(),
  z
    .object({
      binding: adjustmentBinding,
      status: z.literal("REJECTED"),
      confirmedNotApplied: z.literal(true),
      confirmation: confirmationSchema,
    })
    .strict(),
  z
    .object({
      binding: adjustmentBinding,
      status: z.enum(["PENDING", "UNKNOWN"]),
    })
    .strict(),
]);
export type CoverageAdjustmentReceipt = z.infer<typeof receiptSchema>;
export async function readCoverageAdjustmentReceipt(
  value: unknown,
  binding: CoverageAdjustmentBinding,
) {
  const receipt = receiptSchema.parse(value);
  if (coverageAdjustmentKey(receipt.binding) !== coverageAdjustmentKey(binding))
    throw new Error("调整回执与原请求不一致，保护继续保留。");
  if (receipt.status === "APPLIED" || receipt.status === "REJECTED") {
    if (
      (await hashText(JSON.stringify(receipt.confirmation))) !==
        binding.confirmationHash ||
      receipt.confirmation.plan.accountScopeId !== binding.accountScopeId ||
      receipt.confirmation.plan.scopeVersion !== binding.scopeVersion ||
      receipt.confirmation.plan.taskId !== binding.taskId
    )
      throw new Error("回执缺少原确认快照，保护继续保留。");
    if (
      receipt.status === "APPLIED" &&
      (receipt.budgetRevision <= receipt.previousBudgetRevision ||
        receipt.previousBudgetRevision !==
          receipt.confirmation.quote.budgetRevision ||
        receipt.maximum !== receipt.confirmation.quote.newMaxSoubei)
    )
      throw new Error("回执未确认原预算版本与新上限，保护继续保留。");
  }
  return receipt;
}
