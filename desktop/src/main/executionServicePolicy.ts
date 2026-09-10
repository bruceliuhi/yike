import {z} from 'zod';
import {executionOperationSchema, executionSignatureSchema} from '../shared/executionOperation';
import {deviceUuidSchema} from '../shared/deviceRegistration';
import type {ServiceOperation} from './servicePolicy';

const privateExecutionSchema = z.discriminatedUnion('operation', [
  z.object({operation: z.literal('execution.prepare'), payload: z.object({request: executionOperationSchema}).strict()}).strict(),
  z.object({operation: z.literal('execution.apply'), payload: z.object({
    request: executionOperationSchema, signature: executionSignatureSchema,
  }).strict()}).strict(),
  z.object({operation: z.literal('execution.receipt'), payload: z.object({request_id: deviceUuidSchema}).strict()}).strict(),
  z.object({operation: z.literal('execution.task'), payload: z.object({task_id: deviceUuidSchema}).strict()}).strict(),
]);

/** Main only. Public requestApi never accepts these operations or signing material. */
export function validatedExecutionOperation(input: unknown): ServiceOperation | null {
  const parsed = privateExecutionSchema.safeParse(input);
  if (!parsed.success) return null;
  const request = parsed.data;
  switch (request.operation) {
    case 'execution.prepare': return {
      path: '/api/ui/execution-signing-payload', method: 'POST', body: JSON.stringify(request.payload), logout: false,
    };
    case 'execution.apply': return {
      path: '/api/ui/execution-operations', method: 'POST', body: JSON.stringify(request.payload), logout: false,
    };
    case 'execution.receipt': return {
      path: `/api/ui/execution-operations/${request.payload.request_id}`, method: 'GET', logout: false,
    };
    case 'execution.task': return {
      path: `/api/ui/execution-tasks/${request.payload.task_id}`, method: 'GET', logout: false,
    };
  }
}
