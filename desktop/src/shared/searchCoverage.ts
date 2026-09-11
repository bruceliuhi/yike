import {z} from 'zod';
const id=z.string().trim().min(1).max(128).refine(value=>!/[\u0000-\u001f\u007f]/.test(value));
const revision=z.number().int().positive().max(Number.MAX_SAFE_INTEGER);
export const searchCoverageQuerySchema=z.object({
 contractVersion:z.literal(1),requestId:id,taskId:id,profileId:id,profileVersion:revision,
 expectedScope:z.object({userId:id,accountScopeId:id,scopeVersion:revision}).strict(),
}).strict();
