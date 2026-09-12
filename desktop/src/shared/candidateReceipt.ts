import {z} from 'zod';
import {candidateSubmissionSchema, type CandidateSubmission} from './candidateSubmission';
import {deviceUuidSchema} from './deviceRegistration';
import {nativeProgressBatchSchema} from './nativeSearchProgress';
import {publicRevisitSchema} from './publicSourceRevisit';
const receiptSchema = z.object({
  schema_version: z.literal('candidate-receipt-v1'), request_id: z.string(),
  task_id: deviceUuidSchema, run_id: deviceUuidSchema, platform_run_id: deviceUuidSchema,
  accepted_count: z.number().int().min(0).max(100),
  received_at: z.string().datetime({offset: true}).refine(v => !v.startsWith('0000-')),
  native_progress:nativeProgressBatchSchema.optional(),
  public_revisit:publicRevisitSchema.optional(),
  items: z.array(z.object({index: z.number().int().min(0).max(99), candidate_id: deviceUuidSchema,
    version_id: deviceUuidSchema, observation_id: deviceUuidSchema,
    revision: z.number().int().min(1).max(Number.MAX_SAFE_INTEGER)}).strict()).max(100),
}).strict();
export type CandidateReceipt = z.infer<typeof receiptSchema>;
/** Historical acceptance evidence only; never a current execution authorization. */
export function parseCandidateReceipt(raw: unknown, expected: CandidateSubmission): CandidateReceipt {
  try {
    const batch = candidateSubmissionSchema.parse(expected); const receipt = receiptSchema.parse(raw);
    if(JSON.stringify(receipt.native_progress)!==JSON.stringify(batch.native_progress))throw new Error();
    if(JSON.stringify(receipt.public_revisit)!==JSON.stringify(batch.public_revisit))throw new Error();
    if (receipt.request_id !== batch.request_id || receipt.task_id !== batch.execution.task_id ||
        receipt.run_id !== batch.execution.run_id || receipt.platform_run_id !== batch.execution.platform_run_id ||
        receipt.accepted_count !== batch.records.length || receipt.items.length !== batch.records.length ||
        receipt.items.some((item, index) => item.index !== index) ||
        new Set(receipt.items.map(item => item.observation_id)).size !== receipt.items.length) throw new Error();
    return receipt;
  } catch {throw new Error('CANDIDATE_RECEIPT_INVALID');}
}
