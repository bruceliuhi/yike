import {z} from 'zod';
import {deviceUuidSchema as uuid} from './deviceRegistration';
export const FOREGROUND_COLLECTION_CHANNEL='desktop:foreground-collection';
export const foregroundCollectionCommandSchema=z.discriminatedUnion('action',[
 z.object({action:z.literal('CAPABILITIES')}).strict(),
 z.object({action:z.literal('STATUS'),taskId:uuid}).strict(),
 z.object({action:z.literal('RECOVER'),taskId:uuid,humanConfirmed:z.literal(true),retry:z.boolean().optional()}).strict(),
]);
export const foregroundBindingSchema=z.object({mode:z.literal('xhs-foreground-v1'),platform:z.literal('XIAOHONGSHU'),
 connectionId:uuid,connectionVersion:z.number().int().min(1).max(2147483647),deviceId:uuid,accountPublicId:z.string().regex(/^[A-Za-z0-9]{8,32}$/)}).strict();
export const foregroundCollectionResultSchema=z.discriminatedUnion('state',[
 z.object({state:z.literal('AVAILABLE'),binding:foregroundBindingSchema}).strict(),
 z.object({state:z.enum(['UNAVAILABLE','BUSY','SESSION_CHANGED','INVALID_REQUEST','NOT_FOUND'])}).strict(),
 z.object({state:z.literal('STATUS'),taskId:uuid,localState:z.enum(['COLLECTING','INTERRUPTED','UPLOAD_UNKNOWN','FINISH_UNKNOWN','COMPLETED','STOPPED','FAILED']),
  serverStatus:z.enum(['PENDING','RUNNING','CANCELLING','CANCELED','SUCCEEDED']),stopConfirmed:z.boolean(),recordsUsed:z.number().int().min(0),recoverable:z.boolean()}).strict(),
]);
export type ForegroundCollectionCommand=z.infer<typeof foregroundCollectionCommandSchema>;
export type ForegroundCollectionResult=z.infer<typeof foregroundCollectionResultSchema>;
export type ForegroundBinding=z.infer<typeof foregroundBindingSchema>;
