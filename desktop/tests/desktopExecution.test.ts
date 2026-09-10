import {expect, it} from 'vitest';
import {desktopExecutionCommandSchema, desktopExecutionResultSchema} from '../src/shared/desktopExecution';
const id = '00000000-0000-0000-0000-000000000001';
const commands = [
  {action: 'LIST'}, {action: 'RECOVER', requestId: id},
  {action: 'RECOVER', requestId: id, retry: true, humanConfirmed: true},
  {action: 'CANCEL', requestId: id, taskId: id, humanConfirmed: true},
  {action: 'START', requestId: id, profileVersionId: id, strategyVersionId: id, configurationSha256: 'a'.repeat(64),
    targets: [{platform: 'PUBLIC_WEB', access_mode: 'PUBLIC_ANONYMOUS', connection_id: null, connection_version: null}], humanConfirmed: true},
];
it.each(commands)('accepts narrow explicit $action command', command => {
  expect(desktopExecutionCommandSchema.safeParse(command).success).toBe(true);
});
it.each([
  ...commands.map(command => ({...command, userId: 'forged'})),
  ...commands.map(command => ({...command, signing_payload: '{}'})),
  {...commands[4], humanConfirmed: false}, {...commands[4], targets: []},
  {...commands[4], device_id: id}, {...commands[3], humanConfirmed: undefined},
  {action: 'RECOVER', requestId: id, retry: true}, {action: 'CLAIM', requestId: id},
])('rejects unbound or privileged input %#', command => {
  expect(desktopExecutionCommandSchema.safeParse(command).success).toBe(false);
});
it.each([{state:'LIST',requests:[]},{state:'UNKNOWN',requestId:id},{state:'SIGNED_OUT'},
  {state:'FAILED',error:'EXECUTION_SESSION_FAILED'},
  {state:'RECORDED',receipt:{schema_version:'execution-runtime-v1',request_id:id,operation:'CANCEL',task_id:id,run_id:id,status:'CANCELED',stop_confirmed:true}},
])('validates safe $state response', result => {
  expect(desktopExecutionResultSchema.safeParse(result).success).toBe(true);
  expect(desktopExecutionResultSchema.safeParse({...result,signing_payload:'private'}).success).toBe(false);
});
