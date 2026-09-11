import {z} from 'zod';
import {deviceUuidSchema} from './deviceRegistration';

export const RESEARCH_RUNTIME_CONTRACT_VERSION = 1 as const;
export const RESEARCH_RUNTIME_SOURCE_SCOPE = 'V2EX_LATEST_INDEX' as const;
export const RESEARCH_RUNTIME_SOURCE_LABEL = 'V2EX最新主题 · 公开单源研究' as const;
const nonnegative = z.number().int().min(0).max(2_147_483_647);
const effectCountsSchema = z.object({issued:nonnegative,pending:nonnegative,succeeded:nonnegative,failed:nonnegative,unknown:nonnegative})
  .strict().refine(value=>value.issued===value.pending+value.succeeded+value.failed+value.unknown,'issued count mismatch');

export const researchRuntimeCapabilitySchema = z.object({
  contractVersion:z.literal(RESEARCH_RUNTIME_CONTRACT_VERSION),sourceScope:z.literal(RESEARCH_RUNTIME_SOURCE_SCOPE),
  sourceLabel:z.literal(RESEARCH_RUNTIME_SOURCE_LABEL),maxFreshEffectsPerAdvance:z.literal(1),settlementState:z.literal('PENDING'),
}).strict();
export type ResearchRuntimeCapability=z.infer<typeof researchRuntimeCapabilitySchema>;

export const researchRuntimeStatusSchema = z.object({
  contractVersion:z.literal(RESEARCH_RUNTIME_CONTRACT_VERSION),taskId:deviceUuidSchema,runId:deviceUuidSchema,
  phase:z.enum(['QUEUED','RUNNING','STOPPED','CANCELED','COMPLETED']),sourceScope:z.literal(RESEARCH_RUNTIME_SOURCE_SCOPE),
  sourceLabel:z.literal(RESEARCH_RUNTIME_SOURCE_LABEL),acceptedOriginals:nonnegative.nullable(),analyzedOriginals:nonnegative,
  skippedOriginals:nonnegative,candidateIds:z.array(deviceUuidSchema).max(100),canAdvance:z.boolean(),stopCode:z.string().min(1).max(128).nullable(),
  newActionsBlocked:z.boolean(),effectsPending:z.boolean(),usage:z.object({sourceReads:effectCountsSchema,modelCalls:effectCountsSchema,
    actualSoubei:z.null(),settlementState:z.literal('PENDING')}).strict(),
}).strict().refine(value=>new Set(value.candidateIds).size===value.candidateIds.length,'duplicate candidate IDs')
  .refine(value=>value.acceptedOriginals===null||value.analyzedOriginals+value.skippedOriginals<=value.acceptedOriginals,'original counts exceed accepted');
export type ResearchRuntimeStatus=z.infer<typeof researchRuntimeStatusSchema>;
export const researchRuntimeStatusRequestSchema=z.object({taskId:deviceUuidSchema}).strict();
export const researchRuntimeAdvanceRequestSchema=z.object({taskId:deviceUuidSchema,runId:deviceUuidSchema}).strict();
