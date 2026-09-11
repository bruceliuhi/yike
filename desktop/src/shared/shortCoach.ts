import {z} from 'zod';
import {draftMaterialReferencesSchema,type DraftMaterialReference} from './contactDrafts';

const uuid=z.string().uuid(),sha=z.string().regex(/^[a-f0-9]{64}$/);
const text=z.string().max(8000).refine(value=>!value.includes('\0')&&new TextDecoder().decode(new TextEncoder().encode(value))===value);
const url=z.string().max(2048).refine(value=>{try{const parsed=new URL(value);return ['http:','https:'].includes(parsed.protocol)&&!parsed.username&&!parsed.password;}catch{return false;}});
export const coachInputSchema=z.object({
 binding:z.object({accountScope:z.object({id:uuid,version:z.literal(1)}).strict(),
  requestId:uuid,opportunityId:uuid,profileVersionId:uuid,sourceEvidenceVersion:uuid,
  sourceUrl:url,sourceObservedAt:z.string().datetime({offset:true}),channel:z.enum(['comment','dm']),
  draftVersion:z.number().int().min(1).max(2147483647),draftHash:sha,purpose:z.enum(['requirement','materials','scope']),
 }).strict(),content:text,sourceText:text.refine(value=>!!value.trim()),
 materialReferences:draftMaterialReferencesSchema.optional(),
}).strict().refine(value=>!value.materialReferences?.some(ref=>!value.content.includes(ref.quote)));
export function coachPolicy(input:{materialReferences?:DraftMaterialReference[]}){
 return input.materialReferences?.length ? 'short-coach-material-draft-v1' : 'short-coach-public-draft-v1';
}
export const coachPreviewSchema=z.object({inputHash:sha,
 modelProvider:z.string().min(1).max(80).regex(/^[A-Za-z0-9][A-Za-z0-9_.-]*$/),
 modelName:z.string().min(1).max(200).regex(/^[A-Za-z0-9][A-Za-z0-9_.:/-]*$/),
 policyVersion:z.enum(['short-coach-public-draft-v1','short-coach-material-draft-v1']),
}).strict();
export type CoachPreview=z.infer<typeof coachPreviewSchema>;
export const coachDisclosureSchema=coachPreviewSchema.extend({accepted:z.literal(true)});
export type CoachDisclosure=z.infer<typeof coachDisclosureSchema>;
export const coachGenerateSchema=coachInputSchema.safeExtend({disclosure:coachDisclosureSchema})
 .refine(value=>value.disclosure.policyVersion===coachPolicy(value));
export async function coachInputHash(input:{binding:{accountScope:{id:string;version:number};requestId:string;opportunityId:string;profileVersionId:string;sourceEvidenceVersion:string;sourceUrl:string;sourceObservedAt:string;channel:string;draftVersion:number;draftHash:string;purpose:string};content:string;sourceText:string;materialReferences?:DraftMaterialReference[]}){
 const b=input.binding;
 const bytes=new TextEncoder().encode(JSON.stringify([b.accountScope.id,b.accountScope.version,b.requestId,b.opportunityId,
  b.profileVersionId,b.sourceEvidenceVersion,b.sourceUrl,b.sourceObservedAt,b.channel,b.draftVersion,b.draftHash,b.purpose,input.content,input.sourceText,
  ...(input.materialReferences===undefined?[]:[draftMaterialReferencesSchema.parse(input.materialReferences)])]));
 return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');
}
