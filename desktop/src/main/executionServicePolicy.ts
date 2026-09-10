import {z} from 'zod';
import {executionOperationSchema, executionSignatureSchema} from '../shared/executionOperation';
import {deviceUuidSchema} from '../shared/deviceRegistration';
import type {ServiceOperation} from './servicePolicy';

const privateExecutionSchema = z.discriminatedUnion('operation', [
  z.object({operation:z.literal('monitor.support')}).strict(),
  z.object({operation:z.literal('monitor.list')}).strict(),
  z.object({operation:z.literal('monitor.create'),payload:z.object({schema_version:z.literal('monitor-plans-v1'),request_id:deviceUuidSchema,
    profile_version_id:deviceUuidSchema,strategy_version_id:deviceUuidSchema,human_confirmed:z.literal(true)}).strict()}).strict(),
  z.object({operation:z.literal('monitor.state'),payload:z.object({schema_version:z.literal('monitor-plans-v1'),request_id:deviceUuidSchema,
    plan_id:deviceUuidSchema,expected_revision:z.number().int().min(1).max(2_147_483_647),state:z.enum(['ACTIVE','PAUSED']),human_confirmed:z.literal(true)}).strict()}).strict(),
  z.object({operation:z.literal('monitor.receipt'),payload:z.object({request_id:deviceUuidSchema}).strict()}).strict(),
  z.object({operation:z.literal('monitor.pulse'),payload:z.object({schema_version:z.literal('monitor-runtime-v1'),plan_id:deviceUuidSchema,
    device_id:deviceUuidSchema,monitor_session_id:deviceUuidSchema,credential_version:z.number().int().min(1).max(2_147_483_647),
    targets:executionOperationSchema.shape.targets.unwrap().unwrap(),can_start:z.boolean()}).strict()}).strict(),
  z.object({operation:z.literal('execution.support')}).strict(),
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
    case 'monitor.support':return {path:'/api/ui/monitor-runtime/support',method:'GET',logout:false};
    case 'monitor.list':return {path:'/api/ui/monitor-plans',method:'GET',logout:false};
    case 'monitor.create':return {path:'/api/ui/monitor-plans',method:'POST',body:JSON.stringify(request.payload),logout:false};
    case 'monitor.state':return {path:'/api/ui/monitor-plans/state',method:'POST',body:JSON.stringify(request.payload),logout:false};
    case 'monitor.receipt':return {path:`/api/ui/monitor-plan-operations/${request.payload.request_id}`,method:'GET',logout:false};
    case 'monitor.pulse':return {path:'/api/ui/monitor-runtime/pulse',method:'POST',body:JSON.stringify(request.payload),logout:false};
    case 'execution.support': return {path:'/api/ui/execution-support',method:'GET',logout:false};
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
