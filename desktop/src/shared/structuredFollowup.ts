import {z} from 'zod';
const uuid=z.string().uuid(),time=z.string().datetime({offset:true});
const text=z.string().max(500).refine(v=>!v.includes('\0')&&new TextDecoder().decode(new TextEncoder().encode(v))===v);
export const followupWireBinding=z.object({opportunityId:uuid,profileVersionId:uuid,
 action:z.enum(['create','correct','void','mark-read','legacy-create']),targetId:z.union([uuid,z.literal('')]),
 targetRevision:z.number().int().min(0).max(2147483647),requestId:uuid,
}).strict().refine(v=>['create','legacy-create'].includes(v.action)?v.targetId===''&&v.targetRevision===0:!!v.targetId&&v.targetRevision>0);
const fields=z.object({status:z.enum(['CONTACTED','REPLIED','MEETING','QUOTED','LOST','WON']),note:text.refine(v=>!!v.trim()),
 occurredAt:time.nullable(),nextStep:text,nextFollowupAt:time.nullable(),ownerId:uuid}).strict();
export const followupMutationWire=z.object({binding:followupWireBinding,values:fields.optional(),reason:text.optional()}).strict()
 .refine(v=>v.binding.action==='create'?!!v.values&&v.reason===undefined:
  v.binding.action==='correct'?!!v.values&&!!v.reason?.trim():
  v.binding.action==='void'?v.values===undefined&&!!v.reason?.trim():
  v.binding.action==='mark-read'?v.values===undefined&&v.reason===undefined:false);
export const followupRepliesWire=z.object({opportunityId:uuid.optional()}).strict();
