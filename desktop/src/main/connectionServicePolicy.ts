import type {ServiceOperation} from './servicePolicy';
import {z} from 'zod';
import {connectionOperationSchema} from '../shared/connectionOperation';
import {deviceUuidSchema} from '../shared/deviceRegistration';
const schema = z.discriminatedUnion('operation', [
  z.object({operation: z.literal('connections.apply'), payload: connectionOperationSchema}).strict(),
  z.object({operation: z.literal('connections.receipt'), payload: z.object({request_id: deviceUuidSchema}).strict()}).strict(),
  z.object({operation: z.literal('connections.current')}).strict(),
]);
export function validatedConnectionOperation(value: unknown): ServiceOperation | null {
  const result = schema.safeParse(value);
  if (!result.success) return null;
  const input = result.data;
  if (input.operation === 'connections.apply') return {path: '/api/ui/connection-operations', method: 'POST', body: JSON.stringify(input.payload), logout: false};
  return {path: input.operation === 'connections.current' ? '/api/ui/connections' : `/api/ui/connection-operations/${input.payload.request_id}`, method: 'GET', logout: false};
}
