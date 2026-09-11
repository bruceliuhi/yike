import type {YikeDesktopApi} from '../../shared/contracts';
import {desktopExecutionCommandSchema, desktopExecutionResultSchema, type DesktopExecutionCommand, type DesktopExecutionResult} from '../../shared/desktopExecution';
import {ServiceError} from './contracts';

export interface DesktopExecutionService {
  readonly researchContractVersion?: 1;
  execute(command: DesktopExecutionCommand): Promise<DesktopExecutionResult>;
}
const cache = new WeakMap<YikeDesktopApi, DesktopExecutionService>();
export function desktopExecution(bridge: YikeDesktopApi | undefined): DesktopExecutionService | undefined {
  if (!bridge || typeof bridge.executionCommand !== 'function') return undefined;
  const known = cache.get(bridge);
  if (known) return known;
  const invoke = bridge.executionCommand.bind(bridge);
  const service = Object.freeze({researchContractVersion:1 as const,async execute(input: DesktopExecutionCommand): Promise<DesktopExecutionResult> {
    try {
      const command = desktopExecutionCommandSchema.parse(input);
      const result = desktopExecutionResultSchema.parse(await invoke(command));
      const ordinaryList=command.action==='LIST', researchList=command.action==='RESEARCH_LIST';
      if ((ordinaryList !== (result.state === 'LIST') && (ordinaryList || result.state === 'LIST') ||
          researchList !== (result.state === 'RESEARCH_LIST') && (researchList || result.state === 'RESEARCH_LIST')) &&
          !['SESSION_CHANGED', 'SIGNED_OUT', 'BUSY', 'FAILED', 'SERVICE_UNAVAILABLE'].includes(result.state)) throw new Error();
      if ('requestId' in command && result.state === 'UNKNOWN' && result.requestId !== command.requestId) throw new Error();
      if ('requestId' in command && result.state === 'RECORDED') {
        if (result.receipt.request_id !== command.requestId ||
            command.action === 'START' && (result.receipt.operation !== 'START' ||
              result.receipt.platform_runs.length !== command.targets.length ||
              result.receipt.platform_runs.some((run, index) => run.platform !== command.targets[index].platform)) ||
            command.action === 'CANCEL' && (result.receipt.operation !== 'CANCEL' || result.receipt.task_id !== command.taskId)) throw new Error();
      }
      if((command.action==='RESEARCH_START'||command.action==='RESEARCH_RECOVER')&&result.state==='RESEARCH_RECORDED'&&(
        result.receipt.execution.request_id!==command.requestId||command.action==='RESEARCH_START'&&result.receipt.reservation.quote_id!==command.reservation.quote_id))throw new Error();
      if(['RESEARCH_START','RESEARCH_RECOVER'].includes(command.action)!==(result.state==='RESEARCH_RECORDED')&&
          (['RESEARCH_START','RESEARCH_RECOVER'].includes(command.action)||result.state==='RESEARCH_RECORDED')&&
          !['UNKNOWN','SESSION_CHANGED','SIGNED_OUT','BUSY','NOT_FOUND','KEY_MISSING','DEVICE_NOT_READY','FAILED','SERVICE_UNAVAILABLE'].includes(result.state))throw new Error();
      return result;
    } catch { throw new ServiceError('EXECUTION_RESPONSE_INVALID', '执行响应未核实，原请求已保留；请核对原请求，不要重复启动。'); }
  }});
  cache.set(bridge, service);
  return service;
}
