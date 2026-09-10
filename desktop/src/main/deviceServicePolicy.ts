import {z} from 'zod';
import {deviceRegistrationRequestSchema, deviceUuidSchema} from '../shared/deviceRegistration';
import {deviceChallengeRequestSchema, deviceCompletionSchema} from '../shared/deviceProof';
import type {ServiceOperation} from './servicePolicy';

// Main-process-only operations: deliberately absent from the public service policy.
const deviceOperationSchema = z.discriminatedUnion('operation', [
  z.object({operation: z.literal('devices.register'), payload: deviceRegistrationRequestSchema}).strict(),
  z.object({operation: z.literal('devices.registration'), payload: z.object({request_id: deviceUuidSchema}).strict()}).strict(),
  z.object({operation: z.literal('devices.identity'), payload: z.object({device_id: deviceUuidSchema}).strict()}).strict(),
  z.object({operation: z.literal('devices.challenge'), payload: z.object({
    device_id: deviceUuidSchema, request: deviceChallengeRequestSchema,
  }).strict()}).strict(),
  z.object({operation: z.literal('devices.complete'), payload: z.object({
    device_id: deviceUuidSchema, challenge_id: deviceUuidSchema, proof: deviceCompletionSchema,
  }).strict()}).strict(),
  z.object({operation: z.literal('devices.receipt'), payload: z.object({request_id: deviceUuidSchema}).strict()}).strict(),
]);

export function validatedDeviceOperation(input: unknown): ServiceOperation | null {
  const parsed = deviceOperationSchema.safeParse(input);
  if (!parsed.success) return null;
  const request = parsed.data;
  // Materialize route and JSON now; queued operations retain no caller-owned objects.
  switch (request.operation) {
    case 'devices.register': return {
      path: '/api/ui/device-registrations', method: 'POST', body: JSON.stringify(request.payload), logout: false,
    };
    case 'devices.registration': return {
      path: `/api/ui/device-registration-requests/${request.payload.request_id}`, method: 'GET', logout: false,
    };
    case 'devices.identity': return {
      path: `/api/ui/devices/${request.payload.device_id}/identity`, method: 'GET', logout: false,
    };
    case 'devices.challenge': return {
      path: `/api/ui/devices/${request.payload.device_id}/key-challenges`, method: 'POST',
      body: JSON.stringify(request.payload.request), logout: false,
    };
    case 'devices.complete': return {
      path: `/api/ui/devices/${request.payload.device_id}/key-challenges/${request.payload.challenge_id}/complete`,
      method: 'POST', body: JSON.stringify(request.payload.proof), logout: false,
    };
    case 'devices.receipt': return {
      path: `/api/ui/device-key-requests/${request.payload.request_id}`, method: 'GET', logout: false,
    };
  }
}
