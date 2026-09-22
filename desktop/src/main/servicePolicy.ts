import {z} from 'zod';
import {researchUsageRequestSchema} from '../shared/researchUsage';
import {profileSaveSchema} from '../shared/profileMaterialReferences';
import {opportunityBriefQueryWire} from '../shared/opportunityBrief';
import {contactDraftSaveSchema,contactDraftOperationSchema,contactDraftLatestSchema} from '../shared/contactDrafts';
import {coachInputSchema,coachGenerateSchema} from '../shared/shortCoach';
import {followupWireBinding,followupMutationWire,followupRepliesWire} from '../shared/structuredFollowup';
import {searchCoverageQuerySchema} from '../shared/searchCoverage';
import {suggestionPreviewRequestSchema,suggestionRequestSchema,suggestionReceiptRequestSchema} from '../shared/searchSuggestions';
import {taskFeedQuerySchema,taskFeedGetSchema} from '../shared/taskFeed';
import {researchTimelineRequestSchema,researchSimilarRequestSchema} from '../shared/opportunityResearchApi';
import {prepareStrategySchema, confirmStrategySchema, revokeStrategySchema, strategyUuidSchema} from '../shared/researchStrategies';
import {candidateBindingSchema, candidateQuerySchema, candidateReviewRequestSchema, sourceVerificationRequestSchema, candidateRequestIdSchema, type CandidateQueryInput} from '../shared/candidateReviewApi';
import {materialImpactRequestSchema, materialListRequestSchema, materialMutationRequestSchema, materialOperationRequestSchema} from '../shared/materialsApi';
import {researchRuntimeAdvanceRequestSchema,researchRuntimeStatusRequestSchema,researchRuntimeCapabilityRequestSchema,researchRuntimeReadsRequestSchema} from '../shared/researchRuntime';

const empty = z.object({}).strict().optional();
const identifier = z.string().min(1).max(128).regex(/^[A-Za-z0-9_-][A-Za-z0-9_.:-]*$/);
const text = z.string().max(8000).refine(value => value.trim().length > 0);
const phone = z.string().length(11).regex(/^1[0-9]{10}$/);
const schemas = {
  'researchUsage.quote': researchUsageRequestSchema,
  'researchRuntime.capability':researchRuntimeCapabilityRequestSchema,
  'researchRuntime.status':researchRuntimeStatusRequestSchema,
  'researchRuntime.advance':researchRuntimeAdvanceRequestSchema,
  'researchRuntime.reads':researchRuntimeReadsRequestSchema,
  'opportunityBrief.query': opportunityBriefQueryWire,
  'shortCoach.preview': coachInputSchema,
  'followup.list': empty,
  'followup.replies': followupRepliesWire,
  'followup.mutate': followupMutationWire,
  'followup.operation': followupWireBinding,
  'shortCoach.generate': coachGenerateSchema,
  'contactDrafts.save': contactDraftSaveSchema,
  'contactDrafts.operation': contactDraftOperationSchema,
  'contactDrafts.latest': contactDraftLatestSchema,
  'coverage.query': searchCoverageQuerySchema,
  'research.list': empty,
  'research.timeline': researchTimelineRequestSchema,
  'research.similar': researchSimilarRequestSchema,
  'suggestions.preview': suggestionPreviewRequestSchema,
  'suggestions.submit': suggestionRequestSchema,
  'suggestions.receipt': suggestionReceiptRequestSchema,
  'session.get': empty,
  'management.account': empty,
  'management.exportCsv': empty,
  'session.login': z.object({token: z.string().min(1).max(8192)}).strict(),
  'session.logout': empty,
  'session.requestCode': z.object({phone}).strict(),
  'session.loginPhone': z.object({phone, code: z.string().length(6).regex(/^[0-9]{6}$/), trial_code: z.string().max(128).regex(/^(?:[A-Z0-9]{8}|YK-[A-Za-z0-9_-]{32,})$/).optional()}).strict(),
  'session.loginAccess': z.object({access_code:z.string().min(1).max(128).regex(/^[A-Za-z0-9_-]+$/)}).strict(),
  'profiles.list': empty,
  'connections.list': empty,
  'taskFeed.list': taskFeedQuerySchema,
  'taskFeed.get': taskFeedGetSchema,
  'profiles.save': profileSaveSchema,
  'profiles.confirm': z.object({version_id: identifier}).strict(),
  'opportunities.list': empty,
  'opportunities.get': z.object({id: identifier}).strict(),
  'replies.evidence': z.object({opportunityId:z.string().uuid()}).strict(),
  'followups.list': empty,
  'followups.add': z.object({
    opportunity_id: identifier,
    status: z.enum(['CONTACTED', 'REPLIED', 'MEETING', 'QUOTED', 'LOST', 'WON']),
    note: text
  }).strict(),
  'capabilities.get': empty,
  'candidates.list': candidateQuerySchema,
  'candidates.rawEvidence': z.object({candidateId:candidateBindingSchema.shape.candidateId}).strict(),
  'candidates.review': candidateReviewRequestSchema,
  'candidates.verifySource': sourceVerificationRequestSchema,
  'candidates.request': z.object({requestId:candidateRequestIdSchema}).strict(),
  'strategies.prepare': prepareStrategySchema,
  'strategies.confirm': confirmStrategySchema,
  'strategies.revoke': revokeStrategySchema,
  'strategies.receipt': z.object({request_id: strategyUuidSchema}).strict(),
  'strategies.get': z.object({strategy_version_id: strategyUuidSchema}).strict(),
  'materials.list': materialListRequestSchema,
  'materials.mutate': materialMutationRequestSchema,
  'materials.operation': materialOperationRequestSchema,
  'materials.impact': materialImpactRequestSchema,
} as const;

export interface ServiceOperation {
  path: string;
  method: 'GET' | 'POST' | 'DELETE';
  body?: string;
  logout: boolean;
  timeoutMs?: 25_000 | 75_000;
}

export function validatedOperation(input: unknown): ServiceOperation | null {
  const request = z.object({operation: z.enum(Object.keys(schemas) as [keyof typeof schemas, ...(keyof typeof schemas)[]]), payload: z.unknown().optional()}).strict().safeParse(input);
  if (!request.success) return null;
  const {operation, payload} = request.data;
  const parsed = schemas[operation].safeParse(payload);
  if (!parsed.success) return null;
  if (operation === 'opportunityBrief.query' && new TextEncoder().encode(JSON.stringify(parsed.data)).byteLength > 16 * 1024) return null;
  if (operation.startsWith('shortCoach.') && new TextEncoder().encode(JSON.stringify(parsed.data)).byteLength > 96 * 1024) return null;
  if (operation.startsWith('followup.') && new TextEncoder().encode(JSON.stringify(parsed.data)).byteLength > 32 * 1024) return null;
  if (operation === 'contactDrafts.save' && new TextEncoder().encode(JSON.stringify(parsed.data)).byteLength > 96 * 1024) return null;
  if (operation === 'suggestions.submit' && new TextEncoder().encode(JSON.stringify(parsed.data)).byteLength > 32 * 1024) return null;
  if (operation === 'materials.mutate' && new TextEncoder().encode(JSON.stringify(parsed.data)).byteLength > 32 * 1024) return null;
  if (operation.startsWith('strategies.') && new TextEncoder().encode(JSON.stringify(parsed.data)).byteLength > 128 * 1024) return null;
  const data = parsed.data as Record<string, string> | undefined;
  switch (operation) {
    case 'researchUsage.quote': return {path:'/api/ui/research-usage/quote',method:'POST',body:JSON.stringify(parsed.data),logout:false};
    case 'researchRuntime.capability':return {path:'/api/ui/research-execution/capability'+(data?.dynamicResearchVersion?'?dynamic_research_version=1':data?.sourcePlanVersion?'?source_plan_version=1':data?.sourceCatalogVersion?'?source_catalog_version=1':''),method:'GET',logout:false};
    case 'researchRuntime.status':return {path:`/api/ui/research-execution/tasks/${data!.taskId}`,method:'GET',logout:false};
    case 'researchRuntime.advance':return {path:`/api/ui/research-execution/tasks/${data!.taskId}/advance`,method:'POST',
      body:JSON.stringify({runId:data!.runId}),logout:false,timeoutMs:75_000};
    case 'researchRuntime.reads':return {path:`/api/ui/research-execution/tasks/${data!.taskId}/reads?run_id=${data!.runId}&after=${data!.after}&limit=${data!.limit}`,
      method:'GET',logout:false};
    case 'opportunityBrief.query': return {path:'/api/ui/opportunity-brief/query',method:'POST',body:JSON.stringify(parsed.data),logout:false};
    case 'shortCoach.preview':
    case 'shortCoach.generate': return {path:`/api/ui/short-coach/${operation.slice('shortCoach.'.length)}`,method:'POST',body:JSON.stringify(parsed.data),logout:false,timeoutMs:25_000};
    case 'followup.list': return {path:'/api/ui/followup-workspace',method:'GET',logout:false};
    case 'followup.replies': return {path:`/api/ui/followup-workspace/replies${data!.opportunityId?`?opportunityId=${encodeURIComponent(data!.opportunityId)}`:''}`,method:'GET',logout:false};
    case 'followup.mutate':
    case 'followup.operation': return {path:`/api/ui/followup-workspace/${operation.slice('followup.'.length)}`,method:'POST',body:JSON.stringify(parsed.data),logout:false};
    case 'contactDrafts.save': return {path:'/api/ui/contact-drafts',method:'POST',body:JSON.stringify(parsed.data),logout:false};
    case 'contactDrafts.operation': return {path:'/api/ui/contact-drafts/operation',method:'POST',body:JSON.stringify(parsed.data),logout:false};
    case 'contactDrafts.latest': return {path:`/api/ui/opportunities/${encodeURIComponent(data!.opportunityId)}/contact-drafts/${data!.channel}`,method:'GET',logout:false};
    case 'research.list': return {path:'/api/ui/opportunity-research',method:'GET',logout:false};
    case 'coverage.query': return {path:'/api/ui/search-coverage',method:'POST',body:JSON.stringify(parsed.data),logout:false};
    case 'research.timeline':
    case 'research.similar': return {path:`/api/ui/opportunity-research/${operation.slice('research.'.length)}`,method:'POST',body:JSON.stringify(parsed.data),logout:false};
    case 'taskFeed.list': {
      const params=new URLSearchParams();
      for(const [key,value] of Object.entries(parsed.data!))params.set(key,String(value));
      return {path:'/api/ui/execution-task-feed'+(params.size?'?'+params:''),method:'GET',logout:false};
    }
    case 'taskFeed.get': return {path:`/api/ui/execution-task-feed/${data!.taskId}`,method:'GET',logout:false};
    case 'suggestions.preview': return {path:`/api/ui/search-suggestions/preview?profileVersionId=${data!.profile_version_id}`,method:'GET',logout:false};
    case 'suggestions.submit': return {path:'/api/ui/search-suggestions',method:'POST',body:JSON.stringify(parsed.data),logout:false};
    case 'suggestions.receipt': return {path:`/api/ui/search-suggestions/${data!.request_id}`,method:'GET',logout:false};
    case 'materials.list': {
      const value = parsed.data as {profileVersionId:string};
      return {path:`/api/ui/materials?profileVersionId=${encodeURIComponent(value.profileVersionId)}`,method:'GET',logout:false};
    }
    case 'materials.mutate': return {
      path:'/api/ui/materials/mutate',method:'POST',body:JSON.stringify(parsed.data),logout:false,
      ...((parsed.data as {change:{kind:string}}).change.kind === 'parse' ? {timeoutMs:25_000 as const} : {}),
    };
    case 'materials.operation': {
      const value = parsed.data as {profileVersionId:string;requestId:string};
      return {path:`/api/ui/materials/operation?profileVersionId=${encodeURIComponent(value.profileVersionId)}&requestId=${encodeURIComponent(value.requestId)}`,method:'GET',logout:false};
    }
    case 'materials.impact': return {path:'/api/ui/materials/impact',method:'POST',body:JSON.stringify(parsed.data),logout:false};
    case 'candidates.list': {
      const params = new URLSearchParams();
      for (const [key,value] of Object.entries(parsed.data as CandidateQueryInput)) {
        if (value !== undefined) params.set(key,Array.isArray(value)?value.join(','):String(value));
      }
      params.set('evidenceVersion','1');
      const query = params.toString();
      return {path:'/api/ui/candidates'+(query?'?'+query:''),method:'GET',logout:false};
    }
    case 'candidates.review': return {path:'/api/ui/candidate-reviews?evidenceVersion=1',method:'POST',body:JSON.stringify(data),logout:false,
      ...(data!.action === 'ASSESS' ? {timeoutMs:75_000 as const} : {})};
    case 'candidates.rawEvidence': return {path:`/api/ui/raw-candidates/${encodeURIComponent(data!.candidateId)}`,method:'GET',logout:false};
    case 'candidates.verifySource': return {path:'/api/ui/candidate-source-verifications?evidenceVersion=1',method:'POST',body:JSON.stringify(data),logout:false};
    case 'candidates.request': return {path:`/api/ui/candidate-review-requests/${encodeURIComponent(data!.requestId)}?evidenceVersion=1`,method:'GET',logout:false};
    case 'strategies.prepare': return {path: '/api/ui/research-strategies/prepare', method: 'POST', body: JSON.stringify(data), logout: false};
    case 'strategies.confirm': return {path: '/api/ui/research-strategies/confirm', method: 'POST', body: JSON.stringify(data), logout: false};
    case 'strategies.revoke': return {path: '/api/ui/research-strategies/revoke', method: 'POST', body: JSON.stringify(data), logout: false};
    case 'strategies.receipt': return {path: `/api/ui/research-strategy-operations/${data!.request_id}`, method: 'GET', logout: false};
    case 'strategies.get': return {path: `/api/ui/research-strategies/${data!.strategy_version_id}`, method: 'GET', logout: false};
    case 'session.get': return {path: '/api/ui/session', method: 'GET', logout: false};
    case 'management.account': return {path: '/api/ui/management/account', method: 'GET', logout: false};
    case 'management.exportCsv': return {path: '/api/ui/management/export?kind=csv', method: 'GET', logout: false};
    case 'session.login': return {path: '/api/ui/session', method: 'POST', body: JSON.stringify(data), logout: false};
    case 'session.logout': return {path: '/api/ui/session', method: 'DELETE', logout: true};
    case 'session.requestCode': return {path: '/api/ui/auth/sms-code', method: 'POST', body: JSON.stringify(data), logout: false};
    case 'session.loginPhone': return {path: '/api/ui/auth/sms-session', method: 'POST', body: JSON.stringify(data), logout: false};
    case 'session.loginAccess': return {path: '/api/ui/auth/access-session', method: 'POST', body: JSON.stringify(data), logout: false};
    case 'profiles.list': return {path: '/api/ui/profiles', method: 'GET', logout: false};
    case 'connections.list': return {path: '/api/ui/connections', method: 'GET', logout: false};
    case 'profiles.save': return {path: '/api/ui/profiles', method: 'POST', body: JSON.stringify(data), logout: false};
    case 'profiles.confirm': return {path: `/api/ui/profiles/${encodeURIComponent(data!.version_id)}/confirm`, method: 'POST', logout: false};
    case 'opportunities.list': return {path: '/api/ui/opportunities', method: 'GET', logout: false};
    case 'opportunities.get': return {path: `/api/ui/opportunities/${encodeURIComponent(data!.id)}?evidenceVersion=1`, method: 'GET', logout: false};
    case 'followups.list': return {path: '/api/ui/followups', method: 'GET', logout: false};
    case 'followups.add': return {path: '/api/ui/followups', method: 'POST', body: JSON.stringify(data), logout: false};
    case 'capabilities.get': return {path: '/api/ui/capabilities', method: 'GET', logout: false};
    case 'replies.evidence': return {path:`/api/ui/opportunities/${data!.opportunityId}/replies/evidence`,method:'GET',logout:false};
  }
}

export function validatedExternalUrl(input: unknown): string | null {
  if (typeof input !== 'string' || input.length > 8192 || /[\x00-\x20\x7f\\]/.test(input)) return null;
  try {
    const url = new URL(input);
    if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password) return null;
    return url.href;
  } catch { return null; }
}

export function validClipboardText(input: unknown): input is string {
  return typeof input === 'string' && input.length > 0 && input.length <= 20_000 && !input.includes('\0');
}
