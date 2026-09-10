import {desktopExecutionCommandSchema, desktopExecutionResultSchema, type DesktopExecutionResult} from '../shared/desktopExecution';
import {executionOperationSchema} from '../shared/executionOperation';
import {deviceIdentityStatusSchema} from '../shared/deviceIdentity';
import type {createDeviceIdentityController} from './deviceIdentityController';
import type {createExecutionSession} from './executionSession';

export interface ExecutionControllerOptions {
  identity: Pick<ReturnType<typeof createDeviceIdentityController>, 'getStatus' | 'withAuthenticatedSession'>;
  execution: ReturnType<typeof createExecutionSession>;
}
const failed = (): DesktopExecutionResult => ({state: 'FAILED', error: 'EXECUTION_SESSION_FAILED'});

/** Renderer commands never carry identity, device credentials, or arbitrary execution operations. */
export function createExecutionController({identity, execution}: ExecutionControllerOptions) {
  return {async execute(input: unknown): Promise<DesktopExecutionResult> {
    let command;
    try {command = desktopExecutionCommandSchema.parse(input);} catch {return {state: 'INVALID_REQUEST'};}
    try {
      let current = () => false;
      const result = await identity.withAuthenticatedSession<DesktopExecutionResult>(async session => {
        current = session.isCurrent;
        if (command.action === 'LIST') return execution.list(session);
        if (command.action === 'RECOVER' && !command.retry) return execution.recover(session, command.requestId, false);
        // Observe READY only after fresh authentication has invalidated any old-user device state.
        const observed = deviceIdentityStatusSchema.safeParse(identity.getStatus());
        if (!observed.success || observed.data.state !== 'READY') return {state: 'DEVICE_NOT_READY'};
        if (command.action === 'RECOVER') return execution.recover(session, command.requestId, true, {
          deviceId: observed.data.deviceId, credentialVersion: observed.data.credentialVersion,
        });
        const request = executionOperationSchema.parse({
          schema_version: 'execution-runtime-v1', request_id: command.requestId,
          device_id: observed.data.deviceId, credential_version: observed.data.credentialVersion,
          operation: command.action,
          ...(command.action === 'START' ? {
            profile_version_id: command.profileVersionId, strategy_version_id: command.strategyVersionId,
            configuration_sha256: command.configurationSha256, targets: command.targets,
          } : {task_id: command.taskId}),
        });
        return execution.submit(session, request);
      });
      if (result.ok) return current() ? desktopExecutionResultSchema.parse(result.value) : {state: 'SESSION_CHANGED'};
      return result.state === 'FAILED' ? failed() : {state: result.state};
    } catch {return failed();}
  }};
}
