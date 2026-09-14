import {z} from 'zod';
import {executionOperationSchema, type ExecutionOperation} from './executionOperation';
import {deviceUuidSchema} from './deviceRegistration';
import {publicSamplingSchema} from './publicSourceRevisit';
import {nativeProgressClaimSchema} from './nativeSearchProgress';

const envelope = {
  schema_version: z.literal('execution-runtime-v1'),
  request_id: deviceUuidSchema,
  task_id: deviceUuidSchema,
  run_id: deviceUuidSchema,
};
const timestampSchema = z.string().datetime({offset: true}).refine(value =>
  !value.startsWith('0000-') && value === value.trim(), 'invalid execution timestamp');
const startReceiptSchema = z.object({
  ...envelope,
  operation: z.literal('START'),
  status: z.literal('PENDING'),
  stop_confirmed: z.literal(false),
  platform_runs: z.array(z.object({
    platform_run_id: deviceUuidSchema,
    platform: z.enum(['XIAOHONGSHU', 'DOUYIN', 'BILIBILI', 'ZHIHU', 'PUBLIC_WEB']),
    status: z.literal('PENDING'),
  }).strict()).min(1).max(5),
}).strict();
const leaseReceiptSchema = z.object({
  ...envelope,
  operation: z.enum(['CLAIM', 'RENEW']),
  status: z.literal('RUNNING'),
  stop_confirmed: z.literal(false),
  platform_run_id: deviceUuidSchema,
  lease_id: deviceUuidSchema,
  execution_generation: z.number().int().min(1).max(2_147_483_647),
  lease_expires_at: timestampSchema,
  deadline_at: timestampSchema,
  public_sampling: publicSamplingSchema.optional(),
  native_progress:nativeProgressClaimSchema.optional(),
}).strict().refine(receipt=>receipt.public_sampling===undefined||receipt.operation==='CLAIM','sampling is CLAIM-only')
 .refine(receipt=>receipt.native_progress===undefined||receipt.operation==='CLAIM'&&receipt.public_sampling===undefined,'exclusive CLAIM-only progress');
const cancelReceiptSchema = z.object({
  ...envelope,
  operation: z.literal('CANCEL'),
  status: z.enum(['CANCELED', 'CANCELLING']),
  stop_confirmed: z.boolean(),
}).strict().refine(receipt => receipt.stop_confirmed === (receipt.status === 'CANCELED'),
  'invalid execution stop state');
const finishReceiptSchema = z.object({
  ...envelope,
  operation: z.literal('FINISH'),
  status: z.enum(['RUNNING', 'SUCCEEDED']),
  stop_confirmed: z.boolean(),
  platform_run_id: deviceUuidSchema,
  lease_id: deviceUuidSchema,
  execution_generation: z.number().int().min(1).max(2_147_483_647),
  upload_request_id: z.string().min(1).max(128).regex(/^[A-Za-z0-9][A-Za-z0-9_.:-]*$/),
  records_used: z.number().int().min(0).max(10000),
}).strict().refine(receipt => receipt.stop_confirmed === (receipt.status === 'SUCCEEDED'),
  'invalid execution stop state');
const stopReceiptSchema = z.object({
  ...envelope, operation:z.literal('STOP'), status:z.enum(['CANCELLING','CANCELED']),stop_confirmed:z.boolean(),
  platform_run_id:deviceUuidSchema,lease_id:deviceUuidSchema,
  execution_generation:z.number().int().min(1).max(2_147_483_647),
}).strict().refine(receipt=>receipt.stop_confirmed===(receipt.status==='CANCELED'),'invalid execution stop state');
export const executionReceiptSchema = z.discriminatedUnion('operation', [startReceiptSchema, leaseReceiptSchema, cancelReceiptSchema, finishReceiptSchema,stopReceiptSchema]);
const receiptSchema = executionReceiptSchema;
export type ExecutionReceipt = z.infer<typeof receiptSchema>;

function timestampParts(value: string): {milliseconds: number; fraction: string} {
  const parts = /^(.+?)(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})$/.exec(value);
  if (!parts) throw new Error('invalid timestamp');
  const milliseconds = Date.parse(parts[1] + parts[3]);
  if (!Number.isFinite(milliseconds)) throw new Error('invalid timestamp');
  return {milliseconds, fraction: parts[2] ?? ''};
}
function withinDeadline(expires: string, deadline: string): boolean {
  // PostgreSQL emits microseconds; Date alone would truncate and accept small overruns.
  const left = timestampParts(expires);
  const right = timestampParts(deadline);
  if (left.milliseconds !== right.milliseconds) return left.milliseconds < right.milliseconds;
  const precision = Math.max(left.fraction.length, right.fraction.length);
  return left.fraction.padEnd(precision, '0') <= right.fraction.padEnd(precision, '0');
}

/** Historical receipts are readable evidence, not a current lease or renewed authorization. */
export function parseExecutionReceipt(raw: unknown, expected: ExecutionOperation): ExecutionReceipt {
  try {
    const request = executionOperationSchema.parse(expected);
    const receipt = receiptSchema.parse(raw);
    if (receipt.request_id !== request.request_id || receipt.operation !== request.operation) throw new Error('request mismatch');
    if (receipt.operation === 'START') {
      if (!request.targets || receipt.platform_runs.length !== request.targets.length ||
          receipt.platform_runs.some((run, index) => run.platform !== request.targets![index].platform) ||
          new Set(receipt.platform_runs.map(run => run.platform_run_id)).size !== receipt.platform_runs.length) {
        throw new Error('platform mismatch');
      }
    } else {
      if (receipt.task_id !== request.task_id) throw new Error('task mismatch');
      if(receipt.operation==='STOP'&&(receipt.platform_run_id!==request.platform_run_id||
        receipt.lease_id!==request.lease_id||receipt.execution_generation!==request.execution_generation))throw new Error('stop mismatch');
      if (receipt.operation === 'FINISH' && (receipt.platform_run_id !== request.platform_run_id ||
          receipt.lease_id !== request.lease_id || receipt.execution_generation !== request.execution_generation ||
          receipt.upload_request_id !== request.upload_request_id)) throw new Error('finish mismatch');
      if (receipt.operation === 'CLAIM' || receipt.operation === 'RENEW') {
        if ((receipt.public_sampling !== undefined) !== (request.public_sampling_version !== undefined) ||
          receipt.public_sampling?.schema_version !== (request.public_sampling_version===2?'public-sampling-round-v2':request.public_sampling_version===1?'public-sampling-round-v1':undefined)) throw new Error('sampling mismatch');
        if ((receipt.native_progress !== undefined) !== (request.native_progress_version === 1)) throw new Error('progress mismatch');
        if (receipt.platform_run_id !== request.platform_run_id || !withinDeadline(receipt.lease_expires_at, receipt.deadline_at)) {
          throw new Error('lease mismatch');
        }
        if (receipt.operation === 'RENEW' &&
            (receipt.lease_id !== request.lease_id || receipt.execution_generation !== request.execution_generation)) {
          throw new Error('renewal mismatch');
        }
      }
    }
    return receipt;
  } catch { throw new Error('EXECUTION_RECEIPT_INVALID'); }
}
