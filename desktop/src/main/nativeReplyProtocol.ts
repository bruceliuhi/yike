import {z} from 'zod';
import {platformEvent} from '../shared/replyEvidence';
import {executionSignatureSchema} from '../shared/executionOperation';
import type {ServiceOperation} from './servicePolicy';

const uuid=z.string().uuid().regex(/^[a-f0-9-]+$/);
const version=z.number().int().positive().max(2147483647);
const time=z.string().max(48).datetime({offset:true});
const publicId=z.string().regex(/^[a-f0-9]{24}$/);
export const nativeReplyReadSchema=z.object({rootCommentId:publicId,claimedAt:time}).strict();
export type NativeReplyRead=z.infer<typeof nativeReplyReadSchema>;
const batchSchema=z.object({status:z.enum(['COMPLETE','PARTIAL']),items:z.array(z.object({
  externalReplyId:publicId,senderPublicId:publicId,body:z.string().min(1).max(8000),
  receivedAt:time,observedAt:time,readState:z.literal('UNKNOWN'),
}).strict()).max(30)}).strict();
export type NativeReplyBatch=z.infer<typeof batchSchema>;

/** Original buyer's direct replies only. Unknown reads never become an empty success. */
export function parseNativeReplyBatch(raw:unknown,authorPublicId:string,claimedAt:string):NativeReplyBatch {
  const batch=batchSchema.parse(raw),author=publicId.parse(authorPublicId),claim=Date.parse(time.parse(claimedAt));
  const seen=new Set<string>(),now=Date.now();
  if(claim>now+5000)throw new Error('INVALID_REPLY_BATCH');
  for(const item of batch.items){
    const received=Date.parse(item.receivedAt),observed=Date.parse(item.observedAt);
    if(item.senderPublicId!==author||seen.has(item.externalReplyId)||received<claim-5000||received>observed||observed>now+5000)
      throw new Error('INVALID_REPLY_BATCH');
    seen.add(item.externalReplyId);
  }
  return batch;
}

export const nativeReplyRequestSchema=z.object({deviceId:uuid,credentialVersion:version,claimId:uuid,
  contextSha256:z.string().regex(/^[a-f0-9]{64}$/),event:platformEvent,
}).strict();
export type NativeReplyRequest=z.infer<typeof nativeReplyRequestSchema>;
const operations=z.discriminatedUnion('operation',[
  z.object({operation:z.literal('replies.source'),payload:z.object({requestId:uuid,deviceId:uuid,credentialVersion:version}).strict()}).strict(),
  z.object({operation:z.literal('replies.prepare'),payload:z.object({request:nativeReplyRequestSchema}).strict()}).strict(),
  z.object({operation:z.literal('replies.record'),payload:z.object({request:nativeReplyRequestSchema,signature:executionSignatureSchema}).strict()}).strict(),
]);
/** Private main-process routes, deliberately absent from the renderer allowlist. */
export function validatedNativeReplyOperation(input:unknown):ServiceOperation|null {
  const parsed=operations.safeParse(input);if(!parsed.success)return null;
  const routes={'replies.source':'sync-context','replies.prepare':'signing-payload','replies.record':'signed'};
  return {path:`/api/ui/replies/${routes[parsed.data.operation]}`,method:'POST',body:JSON.stringify(parsed.data.payload),logout:false};
}
