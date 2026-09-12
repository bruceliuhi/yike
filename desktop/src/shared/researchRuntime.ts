import {z} from 'zod';
import {deviceUuidSchema} from './deviceRegistration';
import {DEFAULT_PUBLIC_SOURCE,type PublicSourceId} from './publicSources';

export const RESEARCH_RUNTIME_CONTRACT_VERSION = 1 as const;
export const RESEARCH_RUNTIME_SOURCE_SCOPE = 'V2EX_LATEST_INDEX' as const;
export const RESEARCH_RUNTIME_SOURCE_LABEL = 'V2EX最新主题 · 公开单源研究' as const;
const nonnegative = z.number().int().min(0).max(2_147_483_647);
const effectCountsSchema = z.object({issued:nonnegative,pending:nonnegative,succeeded:nonnegative,failed:nonnegative,unknown:nonnegative})
  .strict().refine(value=>value.issued===value.pending+value.succeeded+value.failed+value.unknown,'issued count mismatch');

const legacyCapabilitySchema = z.object({
  contractVersion:z.literal(RESEARCH_RUNTIME_CONTRACT_VERSION),sourceScope:z.literal(RESEARCH_RUNTIME_SOURCE_SCOPE),
  sourceLabel:z.literal(RESEARCH_RUNTIME_SOURCE_LABEL),maxFreshEffectsPerAdvance:z.literal(1),settlementState:z.literal('PENDING'),
}).strict();
const sourceCatalogSchema=z.object({contractVersion:z.literal(2),sourceScope:z.literal('V2EX_SELECTED_INDEX'),
  sourceLabel:z.literal('V2EX定向板块 · 单源索引研究'),sourceIds:z.tuple([
    z.literal('v2ex-latest-v1'),z.literal('v2ex-qna-v1'),z.literal('v2ex-outsourcing-authors-v1')]),
  maxFreshEffectsPerAdvance:z.literal(1),settlementState:z.literal('PENDING')}).strict();
export const researchRuntimeCapabilitySchema=z.union([legacyCapabilitySchema,sourceCatalogSchema]);
export type ResearchRuntimeCapability=z.infer<typeof researchRuntimeCapabilitySchema>;
export function researchAllowsSource(capability:unknown,source:unknown=DEFAULT_PUBLIC_SOURCE){
  const parsed=researchRuntimeCapabilitySchema.safeParse(capability);
  return parsed.success && (parsed.data.contractVersion===1 ? source===DEFAULT_PUBLIC_SOURCE
    : parsed.data.sourceIds.some(id=>id===source));
}
export function researchSourceScope(source:PublicSourceId=DEFAULT_PUBLIC_SOURCE){
  if(source==='v2ex-qna-v1')return 'V2EX问与答 · 单源索引研究（未读评论）' as const;
  if(source==='v2ex-outsourcing-authors-v1')return 'V2EX项目外包 · 单源索引研究（未读作者回复）' as const;
  return RESEARCH_RUNTIME_SOURCE_LABEL;
}
export const researchRuntimeCapabilityRequestSchema=z.object({sourceCatalogVersion:z.literal(1).optional()}).strict().optional();

export const researchRuntimeStatusSchema = z.object({
  contractVersion:z.union([z.literal(1),z.literal(2)]),taskId:deviceUuidSchema,runId:deviceUuidSchema,
  phase:z.enum(['QUEUED','RUNNING','STOPPED','CANCELED','COMPLETED']),sourceScope:z.enum([RESEARCH_RUNTIME_SOURCE_SCOPE,'V2EX_QNA_INDEX','V2EX_OUTSOURCING_INDEX']),
  sourceLabel:z.enum([RESEARCH_RUNTIME_SOURCE_LABEL,'V2EX问与答 · 单源索引研究（未读评论）','V2EX项目外包 · 单源索引研究（未读作者回复）']),acceptedOriginals:nonnegative.nullable(),analyzedOriginals:nonnegative,
  skippedOriginals:nonnegative,candidateIds:z.array(deviceUuidSchema).max(100),canAdvance:z.boolean(),stopCode:z.string().min(1).max(128).nullable(),
  newActionsBlocked:z.boolean(),effectsPending:z.boolean(),usage:z.object({sourceReads:effectCountsSchema,modelCalls:effectCountsSchema,
    resourceCloseout:z.object({state:z.enum(['OPEN','DRAINING','UNCERTAIN','RECORDED']),overduePermits:nonnegative,
      asOf:z.string().datetime({offset:true})}).strict().optional(),
    actualSoubei:z.null(),settlementState:z.literal('PENDING')}).strict(),
}).strict().refine(value=>value.sourceScope===RESEARCH_RUNTIME_SOURCE_SCOPE
  ? value.contractVersion===1&&value.sourceLabel===RESEARCH_RUNTIME_SOURCE_LABEL
  : value.contractVersion===2&&value.sourceLabel===researchSourceScope(value.sourceScope==='V2EX_QNA_INDEX'?'v2ex-qna-v1':'v2ex-outsourcing-authors-v1'),
  'incoherent research source scope')
  .refine(value=>new Set(value.candidateIds).size===value.candidateIds.length,'duplicate candidate IDs')
  .refine(value=>value.acceptedOriginals===null||value.analyzedOriginals+value.skippedOriginals<=value.acceptedOriginals,'original counts exceed accepted')
  .refine(value=>{
    const closeout=value.usage.resourceCloseout;if(!closeout)return true;
    const pending=value.usage.sourceReads.pending+value.usage.modelCalls.pending;
    const unknown=value.usage.sourceReads.unknown+value.usage.modelCalls.unknown;
    if(closeout.overduePermits>pending||value.effectsPending!==(pending>0))return false;
    if((unknown>0||closeout.overduePermits>0)&&closeout.state!=='UNCERTAIN')return false;
    if(closeout.state==='UNCERTAIN'&&(value.canAdvance||!value.newActionsBlocked))return false;
    if(closeout.state==='OPEN'&&pending>0)return false;
    if(closeout.state==='RECORDED'&&(pending>0||unknown>0||value.canAdvance||!value.newActionsBlocked||
      !['STOPPED','CANCELED','COMPLETED'].includes(value.phase)))return false;
    return true;
  },'incoherent resource closeout');
export type ResearchRuntimeStatus=z.infer<typeof researchRuntimeStatusSchema>;
export const researchRuntimeStatusRequestSchema=z.object({taskId:deviceUuidSchema}).strict();
export const researchRuntimeAdvanceRequestSchema=z.object({taskId:deviceUuidSchema,runId:deviceUuidSchema}).strict();
