import {z} from 'zod';
import {draftMaterialReferencesSchema} from './contactDrafts';
import type {OutreachContext} from '../main/outreachConsumer';
import type {createOutreachDispatchSession} from '../main/outreachDispatchSession';

export const NATIVE_OUTREACH_CHANNEL='desktop:native-outreach';
const uuid=z.string().uuid(),sha=z.string().regex(/^[a-f0-9]{64}$/);
export const nativeOutreachDraftSchema=z.object({opportunityId:uuid,channel:z.enum(['comment','dm']),
  content:z.string().min(1).max(8000),savedContent:z.string().max(8000),version:z.number().int().min(1).max(2147483647),
  accountId:z.string().min(1).max(512),recipient:z.string().max(512),materialReferences:draftMaterialReferencesSchema.optional()}).strict();
export const nativeOutreachBindingSchema=z.object({tenantId:uuid,requestId:uuid,claimId:uuid,contextSha256:sha}).strict();
export type NativeOutreachBinding=z.infer<typeof nativeOutreachBindingSchema>;
export const nativeOutreachCommandSchema=z.discriminatedUnion('action',[
  z.object({action:z.literal('PREPARE'),requestId:uuid,draft:nativeOutreachDraftSchema.extend({confirmedFingerprint:z.string().optional()})
    .transform(({confirmedFingerprint:_,...draft})=>draft)}).strict(),
  z.object({action:z.literal('CONFIRM'),flowId:uuid,humanConfirmed:z.literal(true)}).strict(),
  z.object({action:z.literal('CANCEL'),flowId:uuid}).strict(),
  z.object({action:z.literal('RECONCILE'),binding:nativeOutreachBindingSchema}).strict(),
  z.object({action:z.literal('RESUME_RESULT'),binding:nativeOutreachBindingSchema}).strict(),
  z.object({action:z.literal('CANCEL_QUEUED'),binding:nativeOutreachBindingSchema}).strict(),
]);
export type NativeOutreachCommand=z.infer<typeof nativeOutreachCommandSchema>;
export type NativeOutreachError='INVALID_REQUEST'|'BUSY'|'SESSION_CHANGED'|'DEVICE_NOT_READY'|'FLOW_EXPIRED'|
  'DRAFT_CHANGED'|'CONNECTION_CHANGED'|'CHANNEL_UNVERIFIED'|'CONFIRMATION_UNCONFIRMED'|'SOURCE_STOP_FAILED'|'OUTREACH_FAILED';
export type NativeOutreachResult={state:'PREPARED';flowId:string;binding:NativeOutreachBinding;context:OutreachContext}|
  {state:'NOT_SUBMITTED';binding:NativeOutreachBinding;error:NativeOutreachError}|
  {state:'FAILED';error:NativeOutreachError}|{state:'CANCELLED'}|
  {state:'RESULT';binding:NativeOutreachBinding;result:Awaited<ReturnType<ReturnType<typeof createOutreachDispatchSession>['dispatch']>>};
