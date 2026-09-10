import {z} from 'zod';
import {executionOperationSchema, type ExecutionOperation} from './executionOperation';
import {deviceUuidSchema} from './deviceRegistration';

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
}).strict();
const cancelReceiptSchema = z.object({
  ...envelope,
  operation: z.literal('CANCEL'),
  status: z.enum(['CANCELED', 'CANCELLING']),
  stop_confirmed: z.boolean(),
}).strict().refine(receipt => receipt.stop_confirmed === (receipt.status === 'CANCELED'),
  'invalid execution stop state');
export const executionReceiptSchema = z.discriminatedUnion('operation', [startReceiptSchema, leaseReceiptSchema, cancelReceiptSchema]);
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
      if (receipt.operation === 'CLAIM' || receipt.operation === 'RENEW') {
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
