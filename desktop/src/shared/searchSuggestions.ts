import { z } from 'zod';

const uuid = z.string().regex(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
const sha = z.string().regex(/^[0-9a-f]{64}$/);
const provider = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$/);
const model = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}$/);
const policy = z.literal('profile-description-v1');
const bounded = (max:number) => z.string().min(1).max(max).refine(value=>value.trim().length>0);
const count = z.number().int().min(0).max(2147483647);
const strategyText = (max:number) => z.string().refine(value=>Array.from(value).length<=max &&
  /[^\p{C}\p{M}\p{Z}\s]/u.test(value) && !/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\p{Cs}]/u.test(value));
const signalList = (minimum:number) => z.array(strategyText(160)).min(minimum).max(5)
  .refine(values=>new Set(values.map(value=>value.trim().replace(/\s+/g,' ').toLowerCase())).size===values.length);
export const industrySearchStrategySchema = z.object({
  version:z.literal('industry-search-strategy-v1'),
  buyerRole:strategyText(120).nullable(),salesMotion:strategyText(120).nullable(),
  sourceTypes:z.array(z.enum(['SOCIAL_POST','COMMENT','PROCUREMENT','COMPANY_UPDATE','INDUSTRY_SITE'])).min(1).max(5)
    .refine(values=>new Set(values).size===values.length),
  intentSignals:signalList(1),counterSignals:signalList(0),basis:z.array(strategyText(300)).min(1).max(8),
}).strict();
const binding = {request_id:uuid,draft_id:uuid,profile_version_id:uuid,draft_revision:count};

export const suggestionPreviewRequestSchema = z.object({profile_version_id:uuid}).strict();
export const suggestionReceiptRequestSchema = z.object({request_id:uuid}).strict();
export const suggestionRequestSchema = z.object({
  ...binding,
  disclosure:z.object({accepted:z.literal(true),profile_sha256:sha,model_provider:provider,model_name:model,policy_version:policy}).strict(),
}).strict();
export const suggestionPreviewSchema = z.object({
  profile_version_id:uuid,profile_sha256:sha,description:bounded(8000),
  model_provider:provider,model_name:model,disclosure_policy_version:policy,
}).strict();
const resultSchema = z.object({
  keywords:z.array(bounded(80)).min(1).max(20),exclusions:z.array(bounded(80)).max(20),
  rationale:bounded(1200),evidence:z.array(bounded(300)).min(1).max(8),unknowns:z.array(bounded(300)).max(8),
  strategy:industrySearchStrategySchema.optional(),
}).strict();
const usageSchema = z.object({prompt_tokens:count,completion_tokens:count,total_tokens:count}).strict()
  .refine(value=>value.prompt_tokens+value.completion_tokens===value.total_tokens);
export const suggestionNonAdmissionReasons = ['capability_unavailable','disclosure_mismatch','profile_unavailable',
  'suggestion_busy','suggestion_rate_limited','suggestion_quota_exceeded'] as const;
const generationFailures = ['invalid_suggestion_result','suggestion_provider_rejected','profile_changed','dispatch_failed'] as const;
export const suggestionReceiptSchema = z.object({
  ...binding,profile_sha256:sha,model_provider:provider,model_name:model,
  disclosure_policy_version:policy,rule_version:z.literal('search-suggestion-v1'),profile_current:z.boolean(),
  state:z.enum(['PENDING','SUCCEEDED','FAILED','UNKNOWN','NOT_SUBMITTED']),result:resultSchema.nullable(),usage:usageSchema.nullable(),
  error_code:z.enum([...generationFailures,'suggestion_result_unknown',...suggestionNonAdmissionReasons]).nullable(),
  created_at:z.string().datetime({offset:true}),updated_at:z.string().datetime({offset:true}),
}).strict().refine(value=>{
  if(value.state==='SUCCEEDED') return value.result!==null&&value.error_code===null;
  if(value.result!==null||value.usage!==null) return false;
  if(value.state==='PENDING') return value.error_code===null;
  if(value.state==='UNKNOWN') return value.error_code==='suggestion_result_unknown';
  if(value.state==='NOT_SUBMITTED') return value.profile_current===false&&
    suggestionNonAdmissionReasons.some(reason=>reason===value.error_code);
  return generationFailures.some(reason=>reason===value.error_code);
});

export type SuggestionRequest = z.infer<typeof suggestionRequestSchema>;
export type SuggestionPreview = z.infer<typeof suggestionPreviewSchema>;
export type SuggestionReceipt = z.infer<typeof suggestionReceiptSchema>;
