import {z} from 'zod';
const id=z.string().trim().min(1).max(512);
const sourceUrl=z.string().max(2048).refine(value=>{
 try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)&&!u.username&&!u.password;}catch{return false;}
});
export const researchBindingSchema=z.object({
 userId:id,opportunityId:id,profileVersionId:id,sourceUrl,evidenceVersion:id,
 accountScope:z.object({id,version:z.number().int().positive().max(Number.MAX_SAFE_INTEGER)}).strict(),
}).strict();
export const researchTimelineRequestSchema=z.object({binding:researchBindingSchema}).strict();
export const researchSimilarRequestSchema=z.object({binding:researchBindingSchema,requestId:z.string().uuid()}).strict();
