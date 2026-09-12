import {z} from 'zod';
import {deviceUuidSchema} from './deviceRegistration';

const versionSchema = z.number().int().min(1).max(2_147_483_647);
const opaqueSchema = z.string().min(1).max(128).refine(value =>
  /^[A-Za-z0-9]/.test(value) && !/[^A-Za-z0-9_.:-]/.test(value), 'invalid opaque identifier');

const executionTargetSchema = z.object({
  platform: z.enum(['XIAOHONGSHU', 'DOUYIN', 'BILIBILI', 'ZHIHU', 'PUBLIC_WEB']),
  access_mode: z.enum(['PLATFORM_ACCOUNT', 'PUBLIC_ANONYMOUS']),
  // Unlike connection_version, Python's nullable connection_id has no default.
  connection_id: deviceUuidSchema.nullable(),
  connection_version: versionSchema.nullable().default(null),
}).strict().superRefine((target, context) => {
  const valid = target.access_mode === 'PLATFORM_ACCOUNT'
    ? target.connection_id !== null && target.connection_version !== null
    : target.platform === 'PUBLIC_WEB' && target.connection_id === null && target.connection_version === null;
  if (!valid) context.addIssue({code: 'custom', message: 'invalid execution target'});
});

const conditionalFields = ['profile_version_id', 'strategy_version_id', 'configuration_sha256', 'targets',
  'task_id', 'platform_run_id', 'lease_id', 'execution_generation', 'upload_request_id'] as const;
const applicableFields: Record<'START' | 'CLAIM' | 'RENEW' | 'CANCEL' | 'FINISH', readonly string[]> = {
  START: ['profile_version_id', 'strategy_version_id', 'configuration_sha256', 'targets'],
  CLAIM: ['task_id', 'platform_run_id'],
  RENEW: ['task_id', 'platform_run_id', 'lease_id', 'execution_generation'],
  FINISH: ['task_id', 'platform_run_id', 'lease_id', 'execution_generation', 'upload_request_id'],
  CANCEL: ['task_id'],
};

/** Canonical JSON-domain shape shared with pilot.execution_contract.ExecutionOperation. */
export const executionOperationSchema = z.object({
  schema_version: z.literal('execution-runtime-v1'),
  request_id: deviceUuidSchema,
  operation: z.enum(['START', 'CLAIM', 'RENEW', 'CANCEL', 'FINISH']),
  device_id: deviceUuidSchema,
  credential_version: versionSchema,
  profile_version_id: opaqueSchema.nullable().default(null),
  strategy_version_id: opaqueSchema.nullable().default(null),
  configuration_sha256: z.string().length(64).regex(/^[0-9a-f]{64}$/).nullable().default(null),
  targets: z.array(executionTargetSchema).min(1).max(5).nullable().default(null),
  task_id: opaqueSchema.nullable().default(null),
  platform_run_id: opaqueSchema.nullable().default(null),
  lease_id: opaqueSchema.nullable().default(null),
  execution_generation: versionSchema.nullable().default(null),
  upload_request_id: opaqueSchema.nullable().optional(),
  public_sampling_version: z.literal(1).optional(),
  native_progress_version: z.literal(1).optional(),
}).strict().superRefine((request, context) => {
  const applicable = applicableFields[request.operation];
  for (const field of conditionalFields) {
    if ((request[field] != null) !== applicable.includes(field)) {
      context.addIssue({code: 'custom', path: [field], message: 'invalid operation field'});
    }
  }
  if (request.targets && new Set(request.targets.map(target => target.platform)).size !== request.targets.length) {
    context.addIssue({code: 'custom', path: ['targets'], message: 'duplicate execution platform'});
  }
  // Old journal/signature bytes must not acquire a new null field.
  if (request.operation !== 'FINISH') delete request.upload_request_id;
  if (request.public_sampling_version !== undefined && request.operation !== 'CLAIM') {
    context.addIssue({code: 'custom', path: ['public_sampling_version'], message: 'sampling is CLAIM-only'});
  }
  if (request.public_sampling_version === undefined) delete request.public_sampling_version;
  if (request.native_progress_version !== undefined && (request.operation !== 'CLAIM' || request.public_sampling_version !== undefined)) {
    context.addIssue({code:'custom',path:['native_progress_version'],message:'exclusive CLAIM-only progress'});
  }
  if (request.native_progress_version === undefined) delete request.native_progress_version;
});

export type ExecutionOperation = z.infer<typeof executionOperationSchema>;

// 64 bytes produce 86 unpadded base64url characters, with four unused zero bits.
const BASE64URL_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
export const executionSignatureSchema = z.string().length(86).regex(/^[A-Za-z0-9_-]+$/).refine(value => {
  const finalIndex = BASE64URL_ALPHABET.indexOf(value.at(-1) ?? '');
  return finalIndex >= 0 && finalIndex % 16 === 0;
}, 'invalid canonical execution signature');
