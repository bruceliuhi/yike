import {z} from 'zod';
import {executionOperationSchema, executionSignatureSchema} from './executionOperation';
import {deviceUuidSchema} from './deviceRegistration';
import {executionReceiptSchema, parseExecutionReceipt} from './executionReceipt';

const researchStartOperationSchema = executionOperationSchema.refine(request => request.operation === 'START', 'research START required');

/** Outer, main-only authorization. The signed legacy operation remains unchanged. */
export const researchStartEnvelopeSchema = z.object({
  request: researchStartOperationSchema,
  signature: executionSignatureSchema,
  authorization_token: z.string().min(1).max(8192).regex(/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/),
}).strict();

const count = z.number().int().min(1).max(1_000_000);
const sha = z.string().regex(/^[a-f0-9]{64}$/);
/** Non-secret metadata suitable for subsequent receipt recovery, not a START credential. */
export const researchReservationBindingSchema = z.object({
  quote_id: deviceUuidSchema, strategy_version_id: deviceUuidSchema, profile_version_id: deviceUuidSchema,
  configuration_sha256: sha,
  rule_version: z.string().refine(value => value.length > 0 && Array.from(value).length <= 512 && value === value.trim()
    && !/[\p{Cc}\p{Cf}\p{Cs}\p{Zl}\p{Zp}]/u.test(value)),
  rule_sha256: sha, estimated_soubei: z.number().int().nonnegative().max(1_000_000), max_soubei: count,
  limits: z.object({sources: count, minutes: count, modelCalls: count}).strict(),
}).strict().refine(value => value.estimated_soubei <= value.max_soubei, 'reservation exceeds confirmed limit');
export type ResearchReservationBinding = z.infer<typeof researchReservationBindingSchema>;
const researchStartReceiptSchema = z.object({
  schema_version: z.literal('research-execution-v1'), execution: executionReceiptSchema,
  reservation: researchReservationBindingSchema.safeExtend({reservation_id: deviceUuidSchema, status: z.literal('RESERVED')}),
}).strict();

/** A historical reservation receipt never proves current permission to run or actual consumption. */
export function parseResearchStartReceipt(raw: unknown, expectedRequest: unknown, expectedBinding: unknown) {
  try {
    const request = researchStartOperationSchema.parse(expectedRequest);
    const expected = researchReservationBindingSchema.parse(expectedBinding);
    if (request.strategy_version_id !== expected.strategy_version_id ||
        request.profile_version_id !== expected.profile_version_id ||
        request.configuration_sha256 !== expected.configuration_sha256) throw new Error();
    const receipt = researchStartReceiptSchema.parse(raw);
    const execution = parseExecutionReceipt(receipt.execution, request);
    if (execution.operation !== 'START') throw new Error();
    for (const key of ['quote_id', 'strategy_version_id', 'profile_version_id', 'configuration_sha256',
      'rule_version', 'rule_sha256', 'estimated_soubei', 'max_soubei'] as const) {
      if (receipt.reservation[key] !== expected[key]) throw new Error();
    }
    for (const key of ['sources', 'minutes', 'modelCalls'] as const) {
      if (receipt.reservation.limits[key] !== expected.limits[key]) throw new Error();
    }
    return {...receipt, execution};
  } catch { throw new Error('RESEARCH_EXECUTION_RECEIPT_INVALID'); }
}
