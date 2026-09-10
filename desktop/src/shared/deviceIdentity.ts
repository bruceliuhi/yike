import {z} from 'zod';
import {deviceUuidSchema} from './deviceRegistration';

export const GET_DEVICE_IDENTITY_STATUS_CHANNEL = 'desktop:get-device-identity-status';
export const PREPARE_DEVICE_IDENTITY_CHANNEL = 'desktop:prepare-device-identity';
export const deviceIdentityRetrySchema = z.object({
  retryRegistration: z.boolean().optional(),
  retryProof: z.boolean().optional(),
}).strict().default({});
export type DeviceIdentityRetry = z.infer<typeof deviceIdentityRetrySchema>;

export const deviceIdentityStatusSchema = z.discriminatedUnion('state', [
  z.object({state: z.literal('READY'), deviceId: deviceUuidSchema, credentialVersion: z.number().int().positive().max(2_147_483_647)}).strict(),
  z.object({
    state: z.enum(['REGISTRATION_UNKNOWN', 'PROOF_UNKNOWN', 'REVOKED', 'KEY_MISSING', 'KEY_MISMATCH', 'SESSION_CHANGED', 'FAILED']),
    error: z.enum(['DEVICE_IDENTITY_FAILED', 'DEVICE_IDENTITY_VERSION_CHANGED']).optional(),
  }).strict(),
  z.object({state: z.enum(['NOT_PREPARED', 'SIGNED_OUT', 'BUSY', 'SERVICE_UNAVAILABLE', 'INVALID_REQUEST'])}).strict(),
]);
export type DeviceIdentityStatus = z.infer<typeof deviceIdentityStatusSchema>;
