import {z} from 'zod';
import {candidateSubmissionSchema} from '../shared/candidateSubmission';
import {deviceUuidSchema} from '../shared/deviceRegistration';
import {executionSignatureSchema} from '../shared/executionOperation';
import type {ServiceOperation} from './servicePolicy';

const candidateRequestSchema = z.discriminatedUnion('operation', [
  z.object({operation: z.literal('candidate.prepare'), payload: z.object({batch: candidateSubmissionSchema}).strict()}).strict(),
  z.object({operation: z.literal('candidate.apply'), payload: z.object({batch: candidateSubmissionSchema, signature: executionSignatureSchema}).strict()}).strict(),
  z.object({operation: z.literal('candidate.receipt'), payload: z.object({
    platform_run_id: deviceUuidSchema,
    request_id: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/),
  }).strict()}).strict(),
]);

/** Main only; serialize a validated snapshot before queueing. No split or retry of a batch. */
export function validatedCandidateOperation(input: unknown): ServiceOperation | null {
  const parsed = candidateRequestSchema.safeParse(input);
  if (!parsed.success) return null;
  const request = parsed.data;
  if (request.operation === 'candidate.receipt') return {
    path: `/api/ui/candidate-batches/${request.payload.platform_run_id}/${encodeURIComponent(request.payload.request_id)}`,
    method: 'GET', logout: false,
  };
  const body = JSON.stringify(request.payload);
  if (Buffer.byteLength(body, 'utf8') > 4 * 1024 * 1024) return null;
  return {
    path: request.operation === 'candidate.prepare' ? '/api/ui/candidate-submission-signing-payload' : '/api/ui/candidate-batches',
    method: 'POST', body, logout: false,
  };
}
