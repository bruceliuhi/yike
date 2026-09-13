import { z } from "zod";
import type { Session, TaskDraft } from "./models";
import { coverageProvenanceSchema } from "./coverageProvenance";
import {researchSourcePlanSchema} from '../../shared/researchSourcePlan';
import {dynamicScopeSchema} from '../../shared/dynamicResearch';
import {confirmedResearchBindingSchema, type ConfirmedResearchBinding} from '../../shared/researchUsage';

const id = z.string().trim().min(1).max(512);
const count = z.number().int().positive().max(1000000);
export const DEMAND_TYPES = {
  INQUIRY: "明确询价",
  COMPARISON: "方案比较",
  REPLACEMENT: "更换供应商",
  CHANGE: "业务变化",
} as const;
export const researchSettingsSchema = z
  .object({
    version: z.literal(1),
    demandTypes: z
      .array(z.enum(["INQUIRY", "COMPARISON", "REPLACEMENT", "CHANGE"]))
      .min(1)
      .max(4)
      .refine((items) => new Set(items).size === items.length),
    maxSoubei: count.nullable(),
    limits: z
      .object({ sources: count, minutes: count, modelCalls: count })
      .strict(),
    stopAtAnyLimit: z.literal(true),
    evidenceOrder: z.literal("SOURCE_MATCH_CONTEXT"),
    sourcePlan: researchSourcePlanSchema.optional(),
    dynamicScope: dynamicScopeSchema.optional(),
    coverageProvenance: coverageProvenanceSchema.optional(),
    provenance: z
      .object({
        requestId: id,
        suggestionId: id,
        userId: id,
        opportunityId: id,
        profileVersionId: id,
        sourceUrl: z.string().url(),
        evidenceVersion: id,
        accountScope: z.object({ id, version: count }).strict().optional(),
        originalScope: z.string().max(8000),
        additionalScope: z.string().max(8000),
      })
      .strict()
      .optional(),
  })
  .strict();
export type ResearchSettings = z.infer<typeof researchSettingsSchema>;
/** In-progress inputs may be incomplete; never discard a whole draft while a user edits a number. */
export const researchDraftSchema = researchSettingsSchema.extend({
  dynamicScope:z.object({version:z.literal(1),maxAgeDays:z.number().finite(),timezone:z.string()}).strict().optional(),
  demandTypes: z
    .array(z.enum(["INQUIRY", "COMPARISON", "REPLACEMENT", "CHANGE"]))
    .max(4),
  maxSoubei: z.number().finite().nullable(),
  limits: z
    .object({
      sources: z.number().finite(),
      minutes: z.number().finite(),
      modelCalls: z.number().finite(),
    })
    .strict(),
});
export const defaultResearchSettings = (): ResearchSettings => ({
  version: 1,
  demandTypes: ["INQUIRY", "COMPARISON", "REPLACEMENT"],
  // Invited trials should start with a generous visible ceiling so a user can
  // validate the research workflow without first negotiating an allowance.
  // Actual source/model usage is still settled separately by the runtime.
  maxSoubei: 1_000_000,
  limits: { sources: 100, minutes: 15, modelCalls: 50 },
  stopAtAnyLimit: true,
  evidenceOrder: "SOURCE_MATCH_CONTEXT",
});
export interface UsageQuoteRequest {
  contractVersion: 1;
  requestId: string;
  userId: string;
  accountScopeId: string;
  accountScopeVersion: number;
  draftId: string;
  revision: number;
  configurationHash: string;
  maxSoubei: number;
  strategyBinding?: ConfirmedResearchBinding;
}
const quoteSchema = z
  .object({
    contractVersion: z.literal(1),
    requestId: id,
    userId: id,
    accountScopeId: id,
    accountScopeVersion: count,
    draftId: id,
    revision: count,
    configurationHash: z.string().regex(/^[a-f0-9]{64}$/),
    quoteId: id,
    ruleVersion: id,
    authorizationToken: z.string().min(1).max(8192),
    strategyBinding: confirmedResearchBindingSchema.optional(),
    ruleSha256: z.string().length(64).regex(/^[a-f0-9]{64}$/).optional(),
    maxSoubei: count,
    estimatedSoubei: z.number().finite().nonnegative().max(1000000),
    generatedAt: z.string().datetime({ offset: true }),
    expiresAt: z.string().datetime({ offset: true }),
    basis: z.string().trim().min(1).max(2000),
  })
  .strict();
export type UsageQuote = z.infer<typeof quoteSchema>;
export const usageReservationSchema = z
  .object({
    quoteId: id,
    ruleVersion: id,
    maxSoubei: count,
    accountScopeId: id,
    accountScopeVersion: count,
  })
  .strict();
export type UsageReservation = z.infer<typeof usageReservationSchema>;
export function usageReservation(quote: UsageQuote): UsageReservation {
  const {
    quoteId,
    ruleVersion,
    maxSoubei,
    accountScopeId,
    accountScopeVersion,
  } = quote;
  return {
    quoteId,
    ruleVersion,
    maxSoubei,
    accountScopeId,
    accountScopeVersion,
  };
}
export function usageQuoteRequest(
  draft: TaskDraft,
  session: Session,
  configurationHash: string,
  strategyBinding?: ConfirmedResearchBinding,
): UsageQuoteRequest {
  if (
    !session.authenticated ||
    !session.userId ||
    !session.accountScope?.id ||
    !Number.isSafeInteger(session.accountScope.version) ||
    session.accountScope.version < 1
  )
    throw new Error("账户用量范围尚未确认，请重新登录后核对。");
  const research = researchSettingsSchema.parse(draft.research);
  if (strategyBinding && confirmedResearchBindingSchema.parse(strategyBinding).profileVersionId !== draft.profileId)
    throw new Error('确认策略与当前业务画像不一致，请重新确认。');
  if (research.maxSoubei === null)
    throw new Error("请设置本次最多使用的搜贝数。");
  if (research.provenance && research.provenance.userId !== session.userId)
    throw new Error("相似研究草稿不属于当前账户。");
  if (
    research.provenance?.accountScope &&
    (research.provenance.accountScope.id !== session.accountScope.id ||
      research.provenance.accountScope.version !== session.accountScope.version)
  )
    throw new Error("相似研究来源属于其他客户空间，请从当前空间重新选择来源。");
  if (
    research.coverageProvenance &&
    (research.coverageProvenance.userId !== session.userId ||
      research.coverageProvenance.accountScopeId !== session.accountScope.id ||
      research.coverageProvenance.scopeVersion !== session.accountScope.version)
  )
    throw new Error(
      "补查草稿来源属于其他客户空间，请从当前空间重新选择运行记录。",
    );
  return {
    contractVersion: 1,
    requestId: crypto.randomUUID(),
    userId: session.userId,
    accountScopeId: session.accountScope.id,
    accountScopeVersion: session.accountScope.version,
    draftId: draft.id,
    revision: draft.revision,
    configurationHash: z
      .string()
      .regex(/^[a-f0-9]{64}$/)
      .parse(configurationHash),
    maxSoubei: research.maxSoubei,
    ...(strategyBinding ? {strategyBinding: structuredClone(strategyBinding)} : {}),
  };
}
export function parseUsageQuote(
  raw: unknown,
  expected: UsageQuoteRequest,
  now = Date.now(),
): UsageQuote {
  const result = quoteSchema.safeParse(raw);
  if (!result.success)
    throw new Error("用量估算缺少可核验的计量规则，请重试。");
  const quote = result.data;
  const {strategyBinding: expectedStrategy, ...expectedFlat} = expected;
  if (
    Object.entries(expectedFlat).some(
      ([key, value]) => quote[key as keyof UsageQuote] !== value,
    ) || (expectedStrategy ? (!quote.ruleSha256 || !quote.strategyBinding ||
      Object.entries(expectedStrategy).some(([key,value]) => quote.strategyBinding![key as keyof ConfirmedResearchBinding] !== value))
      : quote.strategyBinding !== undefined)
  )
    throw new Error("估算与当前账户、任务或用量上限不一致，请重新估算。");
  if (
    Date.parse(quote.generatedAt) > now ||
    Date.parse(quote.expiresAt) <= now ||
    Date.parse(quote.generatedAt) >= Date.parse(quote.expiresAt)
  )
    throw new Error("本次用量估算已过期，请重新估算。");
  if (quote.estimatedSoubei > quote.maxSoubei)
    throw new Error("预计用量超过本次上限，请缩小范围后重新估算。");
  return quote;
}
export function usageQuoteCurrent(
  quote: UsageQuote | null,
  draft: TaskDraft,
  session: Session,
  now = Date.now(),
) {
  return (
    !!quote &&
    session.authenticated &&
    quote.userId === session.userId &&
    quote.accountScopeId === session.accountScope?.id &&
    quote.accountScopeVersion === session.accountScope?.version &&
    quote.draftId === draft.id &&
    quote.revision === draft.revision &&
    quote.maxSoubei === draft.research?.maxSoubei &&
    Date.parse(quote.expiresAt) > now
  );
}
