import type {YikeService} from '../../src/renderer/services/contracts';
import type {TaskDraft} from '../../src/renderer/domain/models';
import {executionOperationSchema, type ExecutionOperation} from '../../src/shared/executionOperation';
import type {ExecutionReceipt} from '../../src/shared/executionReceipt';

/** TEST-only in-memory UI scenario. No platform, external messages or production authority. */
export function configureExecutionVisual(service:YikeService, draft:TaskDraft) {
  draft.research = undefined;
  const info = service.info;
  service.info = async()=>({...await info(),deviceReady:true});
  service.connections = async()=>[{platform:'web',status:'CONNECTED',capabilities:['search','read']}];
  const requests = new Map<string,ExecutionOperation>();
  const receipts = new Map<string,ExecutionReceipt>();
  const deviceId = '00000000-0000-0000-0000-000000000009';
  service.execution = {async execute(command) {
    if (command.action==='LIST') return {state:'LIST',requests:structuredClone([...requests.values()])};
    if (command.action==='RECOVER') return receipts.has(command.requestId)
      ? {state:'RECORDED',receipt:structuredClone(receipts.get(command.requestId)!)} : {state:'UNKNOWN',requestId:command.requestId};
    const request=executionOperationSchema.parse({schema_version:'execution-runtime-v1',operation:command.action,
      request_id:command.requestId,device_id:deviceId,credential_version:1,
      ...(command.action==='START' ? {profile_version_id:command.profileVersionId,strategy_version_id:command.strategyVersionId,
        configuration_sha256:command.configurationSha256,targets:command.targets} : {task_id:command.taskId})});
    requests.set(request.request_id,request);
    const receipt:ExecutionReceipt=command.action==='START'
      ? {schema_version:'execution-runtime-v1',request_id:request.request_id,operation:'START',task_id:crypto.randomUUID(),run_id:crypto.randomUUID(),
        status:'PENDING',stop_confirmed:false,platform_runs:command.targets.map(target=>({platform_run_id:crypto.randomUUID(),platform:target.platform,status:'PENDING'}))}
      : {schema_version:'execution-runtime-v1',request_id:request.request_id,operation:'CANCEL',task_id:command.taskId,run_id:crypto.randomUUID(),status:'CANCELED',stop_confirmed:true};
    receipts.set(request.request_id,receipt);
    return command.action==='START' ? {state:'UNKNOWN',requestId:request.request_id} : {state:'RECORDED',receipt};
  }};
}
