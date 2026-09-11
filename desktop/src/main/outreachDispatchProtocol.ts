import {z} from 'zod';
import {executionSignatureSchema} from '../shared/executionOperation';
import type {ServiceOperation} from './servicePolicy';

const uuid = z.string().regex(/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
const version = z.number().int().min(1).max(2_147_483_647);
const digest = z.string().regex(/^[0-9a-f]{64}$/);
const awareTime = z.string().max(48).refine(value =>
  /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && !Number.isNaN(Date.parse(value)), 'timezone-aware timestamp required');
const platformReceiptSchema = z.object({
  kind: z.enum(['ACCEPTED', 'REJECTED_NOT_DELIVERED']),
  externalId: z.string().min(1).max(512).regex(/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/),
  sha256: digest,
  observedAt: awareTime,
}).strict();

const outcomeSchema = z.object({
  status: z.enum(['UNKNOWN', 'SENT', 'FAILED']),
  confirmed: z.boolean().nullable().optional().transform(value => value ?? null),
  confirmedNotDelivered: z.boolean().nullable().optional().transform(value => value ?? null),
  proof: platformReceiptSchema.nullable().optional().transform(value => value ?? null),
}).strict().superRefine((outcome, context) => {
  const invalid = outcome.status === 'UNKNOWN'
    ? outcome.confirmed !== null || outcome.confirmedNotDelivered !== null || outcome.proof !== null
    : outcome.confirmed !== true || outcome.proof === null || (outcome.status === 'SENT'
      ? outcome.proof.kind !== 'ACCEPTED' || outcome.confirmedNotDelivered !== null
      : outcome.proof.kind !== 'REJECTED_NOT_DELIVERED' || outcome.confirmedNotDelivered !== true);
  if (invalid) context.addIssue({code: 'custom', message: 'invalid dispatch outcome'});
});

const common = {
  requestId: uuid,
  claimId: uuid,
  deviceId: uuid,
  credentialVersion: version,
  contextSha256: digest,
};

export const dispatchRequestSchema = z.discriminatedUnion('action', [
  z.object({action: z.literal('VALIDATE'), ...common,
    resultId: z.null().optional().transform(() => null),
    outcome: z.null().optional().transform(() => null),
  }).strict(),
  z.object({action: z.literal('CLAIM'), ...common,
    resultId: z.null().optional().transform(() => null),
    outcome: z.null().optional().transform(() => null),
  }).strict(),
  z.object({action: z.literal('RESULT'), ...common, resultId: uuid, outcome: outcomeSchema}).strict(),
]);

export type DispatchRequest = z.infer<typeof dispatchRequestSchema>;

const privateDispatchSchema = z.discriminatedUnion('operation', [
  z.object({operation: z.literal('outreach.dispatch.prepare'), payload: z.object({request: dispatchRequestSchema}).strict()}).strict(),
  z.object({operation: z.literal('outreach.dispatch.apply'), payload: z.object({request: dispatchRequestSchema, signature: executionSignatureSchema}).strict()}).strict(),
  z.object({operation: z.literal('outreach.dispatch.receipt'), payload: z.object({requestId: uuid}).strict()}).strict(),
]);

/** Main-only allowlist. No caller-controlled method or path crosses this boundary. */
export function validatedOutreachDispatchOperation(input: unknown): ServiceOperation | null {
  const parsed = privateDispatchSchema.safeParse(input);
  if (!parsed.success) return null;
  const request = parsed.data;
  if (request.operation === 'outreach.dispatch.receipt') return {
    path: `/api/ui/outreach/queue/${request.payload.requestId}`, method: 'GET', logout: false,
  };
  return {
    path: request.operation === 'outreach.dispatch.prepare'
      ? '/api/ui/outreach/dispatch/signing-payload' : '/api/ui/outreach/dispatch',
    method: 'POST', body: JSON.stringify(request.payload), logout: false,
  };
}
