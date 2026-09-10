import type {YikeDesktopApi} from '../../shared/contracts';
import {desktopExecutionCommandSchema, desktopExecutionResultSchema, type DesktopExecutionCommand, type DesktopExecutionResult} from '../../shared/desktopExecution';
import {ServiceError} from './contracts';

export interface DesktopExecutionService {
  execute(command: DesktopExecutionCommand): Promise<DesktopExecutionResult>;
}
const cache = new WeakMap<YikeDesktopApi, DesktopExecutionService>();
export function desktopExecution(bridge: YikeDesktopApi | undefined): DesktopExecutionService | undefined {
  if (!bridge || typeof bridge.executionCommand !== 'function') return undefined;
  const known = cache.get(bridge);
  if (known) return known;
  const invoke = bridge.executionCommand.bind(bridge);
  const service = Object.freeze({async execute(input: DesktopExecutionCommand): Promise<DesktopExecutionResult> {
    try {
      const command = desktopExecutionCommandSchema.parse(input);
      const result = desktopExecutionResultSchema.parse(await invoke(command));
      if ((command.action === 'LIST') !== (result.state === 'LIST') && (command.action === 'LIST' || result.state === 'LIST') &&
          !['SESSION_CHANGED', 'SIGNED_OUT', 'BUSY', 'FAILED', 'SERVICE_UNAVAILABLE'].includes(result.state)) throw new Error();
      if (command.action !== 'LIST' && result.state === 'UNKNOWN' && result.requestId !== command.requestId) throw new Error();
      if (command.action !== 'LIST' && result.state === 'RECORDED') {
        if (result.receipt.request_id !== command.requestId ||
            command.action === 'START' && (result.receipt.operation !== 'START' ||
              result.receipt.platform_runs.length !== command.targets.length ||
              result.receipt.platform_runs.some((run, index) => run.platform !== command.targets[index].platform)) ||
            command.action === 'CANCEL' && (result.receipt.operation !== 'CANCEL' || result.receipt.task_id !== command.taskId)) throw new Error();
      }
      return result;
    } catch { throw new ServiceError('EXECUTION_RESPONSE_INVALID', '执行响应未核实，原请求已保留；请核对原请求，不要重复启动。'); }
  }});
  cache.set(bridge, service);
  return service;
}
