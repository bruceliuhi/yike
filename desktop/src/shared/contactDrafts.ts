import {z} from 'zod';

const id=z.string().trim().min(1).max(128);
const body=z.string().min(1).max(8000).refine(value=>!!value.trim()&&!value.includes('\0'));
export const draftSaveBindingSchema=z.object({
 opportunityId:id,channel:z.enum(['comment','dm']),requestId:id,
 contentHash:z.string().regex(/^[a-f0-9]{64}$/),
}).strict();
export const contactDraftSchema=z.object({
 opportunityId:id,channel:z.enum(['comment','dm']),content:body,
 savedContent:z.string().max(8000),version:z.number().int().min(1),
 accountId:z.string().max(512),recipient:z.string().max(512),confirmedFingerprint:z.string().optional(),
}).strict();
export const draftSnapshotSchema=z.object({
 draft:contactDraftSchema,
 accountScope:z.object({id,version:z.number().int().min(1)}).strict().nullable(),
 profileVersionId:z.string().max(128),sourceEvidenceVersion:z.string().max(128).nullable(),
}).strict();

// Wire requests are stricter than historical editor/TEST snapshots. Never send
// a local sample id, stale confirmation fingerprint, or caller-selected scope.
const uuid=z.string().uuid();
export const contactDraftOperationSchema=draftSaveBindingSchema.extend({opportunityId:uuid,requestId:uuid});
export const contactDraftLatestSchema=z.object({opportunityId:uuid,channel:z.enum(['comment','dm'])}).strict();
export const contactDraftSaveSchema=z.object({
 binding:contactDraftOperationSchema,
 snapshot:draftSnapshotSchema.extend({
  draft:contactDraftSchema.omit({confirmedFingerprint:true}).extend({opportunityId:uuid,version:z.number().int().min(1).max(2147483647)}),
  accountScope:z.object({id:uuid,version:z.literal(1)}).strict().nullable(),
  profileVersionId:uuid,sourceEvidenceVersion:uuid,
 }),
 previousRequestId:uuid.nullable().optional(),
}).strict().refine(value=>value.binding.opportunityId===value.snapshot.draft.opportunityId&&
 value.binding.channel===value.snapshot.draft.channel);
