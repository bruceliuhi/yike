import {expect, it} from 'vitest';
import {desktopExecutionCommandSchema, desktopExecutionResultSchema} from '../src/shared/desktopExecution';
import {researchReservationBindingSchema} from '../src/shared/researchExecution';
const id = '00000000-0000-0000-0000-000000000001';
const commands = [
  {action: 'LIST'}, {action: 'RECOVER', requestId: id},
  {action: 'RECOVER', requestId: id, retry: true, humanConfirmed: true},
  {action: 'CANCEL', requestId: id, taskId: id, humanConfirmed: true},
  {action: 'START', requestId: id, profileVersionId: id, strategyVersionId: id, configurationSha256: 'a'.repeat(64),
    targets: [{platform: 'PUBLIC_WEB', access_mode: 'PUBLIC_ANONYMOUS', connection_id: null, connection_version: null}], humanConfirmed: true},
  {action: 'RESEARCH_START', requestId: id, profileVersionId: id, strategyVersionId: id,
    configurationSha256: 'a'.repeat(64), targets: [{platform: 'PUBLIC_WEB', access_mode: 'PUBLIC_ANONYMOUS', connection_id: null}],
    reservation: researchReservationBindingSchema.parse({quote_id:id,strategy_version_id:id,profile_version_id:id,
      configuration_sha256:'a'.repeat(64),rule_version:'test-v1',rule_sha256:'b'.repeat(64),estimated_soubei:1,max_soubei:2,
      limits:{sources:1,minutes:1,modelCalls:1}}), authorizationToken:'abc.def', humanConfirmed:true},
  {action: 'RESEARCH_RECOVER', requestId: id}, {action: 'RESEARCH_LIST'},
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
  {...commands[5], authorizationToken: undefined}, {...commands[5], authorizationToken: 'secret'},
  {...commands[6], retry: true},
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

it('validates research results while excluding authorization tokens', () => {
  const request=(commands[5] as any); const record={record_version:2,record_type:'RESEARCH_START',request:{
    schema_version:'execution-runtime-v1',operation:'START',request_id:id,device_id:id,credential_version:1,
    profile_version_id:id,strategy_version_id:id,configuration_sha256:'a'.repeat(64),targets:request.targets},reservation:request.reservation};
  expect(desktopExecutionResultSchema.safeParse({state:'RESEARCH_LIST',requests:[record]}).success).toBe(true);
  expect(desktopExecutionResultSchema.safeParse({state:'RESEARCH_LIST',requests:[{...record,authorizationToken:'abc.def'}]}).success).toBe(false);
});
