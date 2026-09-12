import {z} from 'zod';
import {deviceUuidSchema} from './deviceRegistration';
import {publicSourceIdSchema} from './publicSources';

const topicId=z.string().regex(/^[1-9][0-9]*$/).refine(value=>
  value.length<=16&&value.trim()===value&&Number.isSafeInteger(Number(value)));
const base={plan_id:deviceUuidSchema,source_id:publicSourceIdSchema,round:z.number().int().min(0).max(2_147_483_647)};
export const publicSamplingSchema=z.discriminatedUnion('schema_version',[
  z.object({schema_version:z.literal('public-sampling-round-v1'),...base}).strict(),
  z.object({schema_version:z.literal('public-sampling-round-v2'),...base,
    revisit:z.object({topic_id:topicId,query:z.string().min(1).max(500)}).strict().nullable()}).strict()
    .refine(value=>value.revisit===null||value.source_id==='v2ex-outsourcing-authors-v1'&&value.round%2===1),
]);
export const publicRevisitSchema=z.object({schema_version:z.literal('public-source-revisit-v1'),claim_request_id:deviceUuidSchema,
  topic_id:topicId,outcome:z.enum(['READ','UNAVAILABLE'])}).strict();
export type PublicRevisit=z.infer<typeof publicRevisitSchema>;
