import {z} from 'zod';
import {executionOperationSchema} from './executionOperation';
import {deviceUuidSchema} from './deviceRegistration';
import {executionReceiptSchema} from './executionReceipt';

export const EXECUTION_COMMAND_CHANNEL = 'desktop:execution-command';
export const desktopExecutionCommandSchema = z.discriminatedUnion('action', [
  z.object({action: z.literal('START'), humanConfirmed: z.literal(true), requestId: deviceUuidSchema,
    profileVersionId: deviceUuidSchema, strategyVersionId: deviceUuidSchema,
    configurationSha256: z.string().length(64).regex(/^[0-9a-f]{64}$/),
    targets: executionOperationSchema.shape.targets.unwrap().unwrap(),
  }).strict().refine(value => new Set(value.targets.map(target => target.platform)).size === value.targets.length),
  z.object({action: z.literal('CANCEL'), requestId: deviceUuidSchema, taskId: deviceUuidSchema, humanConfirmed: z.literal(true)}).strict(),
  z.object({action: z.literal('RECOVER'), requestId: deviceUuidSchema, retry: z.boolean().optional(), humanConfirmed: z.literal(true).optional()})
    .strict().refine(value => !value.retry || value.humanConfirmed === true),
  z.object({action: z.literal('LIST')}).strict(),
]);
export type DesktopExecutionCommand = z.infer<typeof desktopExecutionCommandSchema>;
export const desktopExecutionResultSchema = z.discriminatedUnion('state', [
  z.object({state:z.literal('RECORDED'),receipt:executionReceiptSchema}).strict(),
  z.object({state:z.literal('UNKNOWN'),requestId:deviceUuidSchema}).strict(),
  z.object({state:z.literal('LIST'),requests:z.array(executionOperationSchema).max(1000)})
    .strict().refine(value => new Set(value.requests.map(request=>request.request_id)).size===value.requests.length),
  z.object({state:z.enum(['SESSION_CHANGED','BUSY','NOT_FOUND','KEY_MISSING','SIGNED_OUT','DEVICE_NOT_READY','INVALID_REQUEST','SERVICE_UNAVAILABLE'])}).strict(),
  z.object({state:z.literal('FAILED'),error:z.literal('EXECUTION_SESSION_FAILED')}).strict(),
]);
export type DesktopExecutionResult = z.infer<typeof desktopExecutionResultSchema>;
