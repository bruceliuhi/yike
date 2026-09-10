import {describe, expect, it} from 'vitest';
import {createExecutionController} from '../src/main/executionController';
import {createDeviceIdentityController} from '../src/main/deviceIdentityController';
import {executionOperationSchema, type ExecutionOperation} from '../src/shared/executionOperation';
import type {ExecutionSessionResult} from '../src/main/executionSession';
import type {DeviceIdentitySessionInput} from '../src/main/deviceIdentitySession';
import type {ApiResult} from '../src/shared/contracts';

const requestId = '00000000-0000-0000-0000-000000000001';
const deviceId = '00000000-0000-0000-0000-000000000002';
const taskId = '00000000-0000-0000-0000-000000000003';
const profileId = '00000000-0000-0000-0000-000000000004';
const strategyId = '00000000-0000-0000-0000-000000000005';
const ready = {state: 'READY', deviceId, credentialVersion: 3} as const;
const targets = [{platform: 'PUBLIC_WEB', access_mode: 'PUBLIC_ANONYMOUS', connection_id: null, connection_version: null}];
const start = {action: 'START', humanConfirmed: true, requestId, profileVersionId: profileId, strategyVersionId: strategyId, configurationSha256: 'a'.repeat(64), targets};
const cancel = {action: 'CANCEL', humanConfirmed: true, requestId, taskId};
const ok = (data: unknown): ApiResult => ({ok: true, status: 200, data});
const auth = () => ok({authenticated: true, user_id: 'TEST-owner'});
function fixture() {
  const state = {
    publicCalls: [] as unknown[], calls: [] as {method: string; session: DeviceIdentitySessionInput; request?: unknown; retry?: unknown}[],
    sessionRead: async (): Promise<ApiResult> => auth(),
    result: {state: 'UNKNOWN', requestId} as ExecutionSessionResult,
    execute: async (): Promise<ExecutionSessionResult> => state.result,
  };
  const identity = createDeviceIdentityController({service: {
    async request(input) {state.publicCalls.push(input); return state.sessionRead();}, async requestDevice() {return ok({});},
  }, identityFactory: () => ({async prepare() {return ready;}})});
  const execution = {
    async submit(session: DeviceIdentitySessionInput, request: unknown) {state.calls.push({method: 'submit', session, request}); return state.execute();},
    async recover(session: DeviceIdentitySessionInput, request: unknown, retry?: unknown) {state.calls.push({method: 'recover', session, request, retry}); return state.execute();},
    async list(session: DeviceIdentitySessionInput) {state.calls.push({method: 'list', session}); return state.execute();},
  };
  return {state, identity, controller: createExecutionController({identity, execution})};
}

describe('narrow desktop execution controller', () => {
  it.each([start, cancel])('builds $action using only the authenticated main-process READY device/version', async command => {
    const f = fixture(); expect(await f.identity.prepare()).toEqual(ready);
    expect(await f.controller.execute(command)).toEqual({state: 'UNKNOWN', requestId});
    expect(f.state.calls).toHaveLength(1); const call = f.state.calls[0]; expect(call.method).toBe('submit');
    expect(call.session.userId).toBe('TEST-owner'); expect(call.session.isCurrent()).toBe(true);
    expect(call.request).toEqual(executionOperationSchema.parse({schema_version: 'execution-runtime-v1', request_id: requestId, device_id: deviceId, credential_version: 3, operation: command.action,
      ...(command.action === 'START' ? {profile_version_id: profileId, strategy_version_id: strategyId, configuration_sha256: 'a'.repeat(64), targets} : {task_id: taskId})}));
  });
  it.each([start, cancel])('requires READY for $action without automatically preparing a device', async command => {
    const f = fixture(); expect(await f.controller.execute(command)).toEqual({state: 'DEVICE_NOT_READY'});
    expect(f.state.calls).toEqual([]); expect(f.identity.getStatus()).toEqual({state: 'NOT_PREPARED'});
  });
  it('fresh authentication for a changed user invalidates old READY before constructing START', async () => {
    const f = fixture(); expect(await f.identity.prepare()).toEqual(ready);
    f.state.sessionRead = async () => ok({authenticated: true, user_id: 'TEST-other'});
    expect(await f.controller.execute(start)).toEqual({state: 'DEVICE_NOT_READY'}); expect(f.state.calls).toEqual([]);
  });
  it.each([{action: 'LIST'}, {action: 'RECOVER', requestId}, {action: 'RECOVER', requestId, retry: true, humanConfirmed: true}])('allows historical $action without READY and never substitutes the original operation', async command => {
    const f = fixture(); expect(await f.controller.execute(command)).toEqual({state: 'UNKNOWN', requestId});
    expect(f.state.calls).toHaveLength(1); const call = f.state.calls[0];
    expect(call.method).toBe(command.action === 'LIST' ? 'list' : 'recover');
    if (command.action === 'RECOVER') {expect(call.request).toBe(requestId); expect(call.retry).toBe('retry' in command ? true : false);}
    expect(f.identity.getStatus()).toEqual({state: 'NOT_PREPARED'});
  });
  it.each([null, [], {}, {action: 'CLAIM'}, {action: 'RENEW'}, {...start, deviceId}, {...start, credentialVersion: 9}, {...start, userId: 'forged'}, {...start, humanConfirmed: false}, {...cancel, sessionId: requestId}, {action: 'RECOVER', requestId, retry: true}, {action: 'LIST', url: 'https://other.example'}])('rejects malformed or privileged command %# before authentication or storage', async command => {
    const f = fixture(); expect(await f.controller.execute(command)).toEqual({state: 'INVALID_REQUEST'});
    expect(f.state.publicCalls).toEqual([]); expect(f.state.calls).toEqual([]);
  });
  it('snapshots the entire renderer command before the authentication await', async () => {
    const f = fixture(); expect(await f.identity.prepare()).toEqual(ready);
    let release!: (result: ApiResult) => void; const blocked = new Promise<ApiResult>(resolve => {release = resolve;}); f.state.sessionRead = async () => blocked;
    const command = structuredClone(start); const pending = f.controller.execute(command);
    command.requestId = taskId; command.configurationSha256 = 'b'.repeat(64); command.targets[0].platform = 'DOUYIN';
    release(auth()); expect(await pending).toEqual({state: 'UNKNOWN', requestId});
    const saved = f.state.calls[0].request as ExecutionOperation;
    expect(saved.request_id).toBe(requestId); expect(saved.configuration_sha256).toBe('a'.repeat(64)); expect(saved.targets?.[0].platform).toBe('PUBLIC_WEB');
  });
  it('keeps LIST and RECORDED receipts as historical output, without granting READY', async () => {
    const f = fixture(); f.state.result = {state: 'LIST', requests: []};
    expect(await f.controller.execute({action: 'LIST'})).toEqual(f.state.result);
    f.state.result = {state: 'RECORDED', receipt: {schema_version: 'execution-runtime-v1', request_id: requestId, operation: 'CANCEL', task_id: taskId, run_id: deviceId, status: 'CANCELED', stop_confirmed: true}};
    expect(await f.controller.execute({action: 'RECOVER', requestId})).toEqual(f.state.result);
    expect(f.identity.getStatus()).toEqual({state: 'NOT_PREPARED'});
  });
  it('passes through SIGNED_OUT from real session authentication without execution calls', async () => {
    const f = fixture(); f.state.sessionRead = async () => ({ok: false, status: 401, error: 'invalid_session'});
    expect(await f.controller.execute({action: 'LIST'})).toEqual({state: 'SIGNED_OUT'}); expect(f.state.calls).toEqual([]);
  });
  it('sanitizes unexpected execution errors and allows a later action', async () => {
    const f = fixture(); f.state.execute = async () => {throw new Error('/private/key');};
    expect(await f.controller.execute({action: 'LIST'})).toEqual({state: 'FAILED', error: 'EXECUTION_SESSION_FAILED'});
    f.state.execute = async () => ({state: 'LIST', requests: []});
    expect(await f.controller.execute({action: 'LIST'})).toEqual({state: 'LIST', requests: []});
  });
  it('rejects extra private fields in coordinator output without altering the original record', async () => {
    const f = fixture();
    const stored = {state: 'UNKNOWN' as const, requestId, privatePayload: '/private/key'};
    f.state.execute = async () => stored;
    expect(await f.controller.execute({action: 'RECOVER', requestId})).toEqual({state: 'FAILED', error: 'EXECUTION_SESSION_FAILED'});
    expect(stored).toEqual({state: 'UNKNOWN', requestId, privatePayload: '/private/key'});
    expect(f.state.calls.map(call => call.method)).toEqual(['recover']);
  });
  it('suppresses a late old-account result and blocks duplicate commands until the operation settles', async () => {
    const f = fixture(); let release!: (value: ExecutionSessionResult) => void; let started!: () => void;
    const begun = new Promise<void>(resolve => {started = resolve;}); const blocked = new Promise<ExecutionSessionResult>(resolve => {release = resolve;});
    f.state.execute = async () => {started(); return blocked;}; const pending = f.controller.execute({action: 'LIST'});
    await Promise.race([begun, pending]); expect(f.state.calls).toHaveLength(1);
    expect(await f.controller.execute({action: 'LIST'})).toEqual({state: 'BUSY'});
    await f.identity.requestApi({operation: 'session.logout'}); release({state: 'LIST', requests: []});
    expect(await pending).toEqual({state: 'SESSION_CHANGED'});
  });
  it('rechecks the captured epoch after the authenticated wrapper resolves but before returning its value', async () => {
    const f = fixture();
    const controller = createExecutionController({identity: {
      getStatus: f.identity.getStatus,
      async withAuthenticatedSession(action) {
        const result = await f.identity.withAuthenticatedSession(action);
        await f.identity.requestApi({operation: 'session.logout'});
        return result;
      },
    }, execution: {
      async list() {return {state: 'LIST', requests: []};},
      async submit() {return {state: 'UNKNOWN', requestId};},
      async recover() {return {state: 'UNKNOWN', requestId};},
    }});
    expect(await controller.execute({action: 'LIST'})).toEqual({state: 'SESSION_CHANGED'});
  });
});
