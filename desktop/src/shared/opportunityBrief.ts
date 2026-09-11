import {z} from 'zod';
const uuid=z.string().uuid();
export const opportunityBriefQueryWire=z.object({
 contractVersion:z.literal(1),requestId:uuid,userId:uuid,accountScopeId:uuid,
 scopeVersion:z.literal(1),profileId:uuid,profileVersion:z.number().int().positive().max(2_147_483_647),
 businessDate:z.string().regex(/^\d{4}-\d{2}-\d{2}$/),timezone:z.string().min(1).max(100),
}).strict();
