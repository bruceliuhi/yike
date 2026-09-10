import {z} from 'zod';
import {nativeLoginPlatformSchema} from './platformAccount';

export const PLATFORM_CONNECTION_CHANNEL = 'desktop:platform-connection-command';
const platform = nativeLoginPlatformSchema;
const flowId = z.string().uuid();
const id = z.string().min(1).max(256).refine(value => value.trim() === value && !/[\p{Cc}\p{Cf}\p{Cs}]/u.test(value));
const timestamp = z.string().datetime({offset: true});

export const platformConnectionCommandSchema = z.union([
  z.strictObject({action: z.literal('OPEN'), platform}),
  z.strictObject({action: z.literal('CHECK'), platform, flowId}),
  z.strictObject({action: z.literal('CANCEL'), platform, flowId}),
]);
export type PlatformConnectionCommand = z.infer<typeof platformConnectionCommandSchema>;

/** Exact GET /connections row. Registration does not grant execution capabilities. */
export const connectionRegistryRowSchema = z.strictObject({
  connection_id: id, device_id: id, account_public_id: id,
  platform: z.enum(['XIAOHONGSHU', 'DOUYIN', 'BILIBILI', 'ZHIHU', 'PUBLIC_WEB']),
  status: z.enum(['UNVERIFIED', 'CONNECTED', 'DISCONNECTED', 'EXPIRED']),
  connection_version: z.number().int().min(1).max(2_147_483_647),
  connected_at: timestamp, disconnected_at: timestamp.nullable(),
});
export type ConnectionRegistryRow = z.infer<typeof connectionRegistryRowSchema>;
export const platformConnectionResultSchema = z.union([
  z.strictObject({state: z.enum(['OPENED', 'WAITING_LOGIN', 'UNKNOWN', 'CANCELLED']), flowId}),
  z.strictObject({state: z.literal('CONNECTED'), flowId, connection: connectionRegistryRowSchema
    .refine(row => row.status === 'CONNECTED' && nativeLoginPlatformSchema.safeParse(row.platform).success)}),
  z.strictObject({state: z.literal('FAILED'), error: z.enum(['CONNECTION_FAILED', 'SOURCE_STOP_FAILED',
    'LOGIN_EXPIRED', 'ACCOUNT_MISMATCH', 'CURRENT_CONNECTION_CHANGED'])}),
  z.strictObject({state: z.enum(['INVALID_REQUEST', 'SESSION_CHANGED', 'SIGNED_OUT',
    'DEVICE_NOT_READY', 'BUSY', 'SERVICE_UNAVAILABLE'])}),
]);
export type PlatformConnectionResult = z.infer<typeof platformConnectionResultSchema>;
