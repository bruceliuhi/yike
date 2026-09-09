import { coverageFixture } from "./r4-search-coverage-fixtures";
import {
  coveragePlan,
  type CoveragePlanRequest,
} from "../../src/renderer/domain/searchCoverage";
import { newTaskDraft } from "../../src/renderer/domain/models";
import { defaultResearchSettings } from "../../src/renderer/domain/researchUsage";
import type {
  CoverageAdjustmentBinding,
  CoverageAdjustmentReceipt,
  CoveragePlanPreview,
  CoveragePreviewRequest,
} from "../../src/renderer/domain/coveragePlan";

export const planFor = (
  kind: CoveragePlanRequest["kind"],
): CoveragePlanRequest => {
  const snapshot = coverageFixture();
  snapshot.usage = {
    unit: "SOUBEI",
    ruleVersion: "TEST-rule",
    budgetRevision: 1,
    estimated: 50,
    maximum: 50,
    actual: 50,
    settlement: "RESERVED",
  };
  snapshot.units[1].recovery =
    kind === "NEW_DRAFT" ? "TERMINAL" : "RESUMABLE_CONFIRMED";
  return coveragePlan(snapshot, snapshot.units[1])!;
};
export function previewFor(input: CoveragePreviewRequest): CoveragePlanPreview {
  const common = {
    requestId: input.requestId,
    plan: input.plan,
    previewId: "TEST-preview",
    generatedAt: new Date().toISOString(),
    expiresAt: input.plan.expiresAt,
    scopeSummary: "TEST 已确认未查范围",
  };
  return input.plan.kind === "NEW_DRAFT"
    ? {
        ...common,
        kind: "NEW_DRAFT",
        recovery: "TERMINAL",
        draft: {
          ...newTaskDraft("monitor"),
          id: "TEST-source-draft",
          revision: input.plan.configurationRevision,
          name: "TEST未查范围",
          profileId: input.plan.profileId,
          profileVersion: input.plan.profileVersion,
          terms: [
            {
              id: "TEST-term",
              value: "TEST询价",
              origin: "manual",
              edited: true,
            },
          ],
          platforms: ["douyin"],
          research: { ...defaultResearchSettings(), maxSoubei: 50 },
        },
      }
    : {
        ...common,
        kind: "ADJUST_LIMIT",
        recovery: "RESUMABLE_CONFIRMED",
        quote: {
          quoteId: "TEST-quote",
          ruleVersion: "TEST-rule",
          authorizationToken: "TEST-private-proof",
          accountScopeId: input.plan.accountScopeId,
          scopeVersion: input.plan.scopeVersion,
          taskId: input.plan.taskId,
          runId: input.plan.runId,
          budgetRevision: input.plan.budgetRevision!,
          oldMaxSoubei: 50,
          newMaxSoubei: input.newMaxSoubei!,
          additionalSoubei: input.newMaxSoubei! - 50,
          estimatedAdditionalSoubei: null,
          expiresAt: input.plan.expiresAt,
        },
      };
}
export function applied(
  binding: CoverageAdjustmentBinding,
  preview: CoveragePlanPreview,
): CoverageAdjustmentReceipt {
  if (preview.kind !== "ADJUST_LIMIT") throw new Error("TEST adjustment only");
  const { authorizationToken: _token, ...quote } = preview.quote;
  return {
    binding,
    status: "APPLIED",
    notResumed: true,
    previousBudgetRevision: quote.budgetRevision,
    budgetRevision: quote.budgetRevision + 1,
    maximum: quote.newMaxSoubei,
    confirmation: { ...preview, quote },
  };
}
