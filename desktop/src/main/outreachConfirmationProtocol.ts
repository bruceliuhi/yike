import {z} from 'zod';
import {executionSignatureSchema} from '../shared/executionOperation';
import type {ServiceOperation} from './servicePolicy';
const uuid=z.string().uuid(),sha=z.string().regex(/^[a-f0-9]{64}$/),version=z.number().int().min(1).max(2147483647);
export const draftBindingSchema=z.object({opportunityId:uuid,channel:z.enum(['comment','dm']),requestId:uuid,contentHash:sha}).strict();
export const outreachContextInputSchema=z.object({binding:draftBindingSchema,deviceId:uuid,connectionId:uuid,connectionVersion:version}).strict();
export const outreachConfirmationSchema=z.object({requestId:uuid,context:outreachContextInputSchema,contextSha256:sha,
  credentialVersion:version,humanConfirmed:z.literal(true),channelCheck:z.object({status:z.literal('AVAILABLE'),observedAt:z.string().max(48).datetime({offset:true})}).strict()}).strict();
export type OutreachConfirmation=z.infer<typeof outreachConfirmationSchema>;
const command=z.discriminatedUnion('operation',[
  z.object({operation:z.literal('outreach.draft.latest'),payload:z.object({opportunityId:uuid,channel:z.enum(['comment','dm'])}).strict()}).strict(),
  z.object({operation:z.literal('outreach.context'),payload:outreachContextInputSchema}).strict(),
  z.object({operation:z.literal('outreach.confirmation.prepare'),payload:z.object({request:outreachConfirmationSchema}).strict()}).strict(),
  z.object({operation:z.literal('outreach.confirmation.apply'),payload:z.object({request:outreachConfirmationSchema,signature:executionSignatureSchema}).strict()}).strict(),
  z.object({operation:z.literal('outreach.confirmation.cancel'),payload:z.object({requestId:uuid}).strict()}).strict(),
]);
export function validatedOutreachConfirmationOperation(raw:unknown):ServiceOperation|null {
  const parsed=command.safeParse(raw);if(!parsed.success)return null;const c=parsed.data;
  if(c.operation==='outreach.draft.latest')return {path:`/api/ui/opportunities/${c.payload.opportunityId}/contact-drafts/${c.payload.channel}`,method:'GET',logout:false};
  if(c.operation==='outreach.confirmation.cancel')return {path:`/api/ui/outreach/queue/${c.payload.requestId}/cancel`,method:'POST',logout:false};
  return {path:c.operation==='outreach.context'?'/api/ui/outreach/context':c.operation==='outreach.confirmation.prepare'?'/api/ui/outreach/signing-payload':'/api/ui/outreach/queue',method:'POST',body:JSON.stringify(c.payload),logout:false};
}
