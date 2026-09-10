import { z } from 'zod';

const uuid = z.string().regex(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
const sha = z.string().regex(/^[0-9a-f]{64}$/);
const provider = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$/);
const model = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}$/);
const policy = z.literal('profile-description-v1');
const bounded = (max:number) => z.string().min(1).max(max).refine(value=>value.trim().length>0);
const count = z.number().int().min(0).max(2147483647);
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
}).strict();
const usageSchema = z.object({prompt_tokens:count,completion_tokens:count,total_tokens:count}).strict()
  .refine(value=>value.prompt_tokens+value.completion_tokens===value.total_tokens);
export const suggestionReceiptSchema = z.object({
  ...binding,profile_sha256:sha,model_provider:provider,model_name:model,
  disclosure_policy_version:policy,rule_version:z.literal('search-suggestion-v1'),profile_current:z.boolean(),
  state:z.enum(['PENDING','SUCCEEDED','FAILED','UNKNOWN']),result:resultSchema.nullable(),usage:usageSchema.nullable(),
  error_code:z.enum(['invalid_suggestion_result','suggestion_provider_rejected','profile_changed','dispatch_failed','suggestion_result_unknown']).nullable(),
  created_at:z.string().datetime({offset:true}),updated_at:z.string().datetime({offset:true}),
}).strict().refine(value=>{
  if(value.state==='SUCCEEDED') return value.result!==null&&value.error_code===null;
  if(value.result!==null||value.usage!==null) return false;
  if(value.state==='PENDING') return value.error_code===null;
  if(value.state==='UNKNOWN') return value.error_code==='suggestion_result_unknown';
  return value.error_code!==null&&value.error_code!=='suggestion_result_unknown';
});

export type SuggestionRequest = z.infer<typeof suggestionRequestSchema>;
export type SuggestionPreview = z.infer<typeof suggestionPreviewSchema>;
export type SuggestionReceipt = z.infer<typeof suggestionReceiptSchema>;
