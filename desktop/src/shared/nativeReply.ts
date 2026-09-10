import {z} from 'zod';

export const NATIVE_REPLY_CHANNEL='desktop:native-reply';
const uuid=z.string().uuid();
export const nativeReplyCommandSchema=z.object({
  action:z.literal('SYNC'),
  opportunityId:uuid,
  requestId:uuid,
}).strict();
export type NativeReplyCommand=z.infer<typeof nativeReplyCommandSchema>;
export const nativeReplyErrorSchema=z.enum([
  'INVALID_REQUEST','BUSY','SESSION_CHANGED','DEVICE_NOT_READY','CONNECTION_CHANGED',
  'SOURCE_UNAVAILABLE','SOURCE_STOP_FAILED','REPLY_SYNC_FAILED',
]);
export const nativeReplyResultSchema=z.discriminatedUnion('state',[
  z.object({state:z.literal('SYNCED'),requestId:uuid,coverage:z.enum(['COMPLETE','PARTIAL']),observed:z.number().int().nonnegative(),recorded:z.number().int().nonnegative()}).strict(),
  z.object({state:z.literal('FAILED'),error:nativeReplyErrorSchema,recorded:z.number().int().nonnegative()}).strict(),
]);
export type NativeReplyError=z.infer<typeof nativeReplyErrorSchema>;
export type NativeReplyResult=z.infer<typeof nativeReplyResultSchema>;
