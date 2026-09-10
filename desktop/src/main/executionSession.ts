import type {DeviceIdentitySessionInput} from './deviceIdentitySession';
import type {ExecutionJournal} from './executionJournal';
import type {DeviceKeyMaterial, DeviceKeyScope} from './deviceKeyVault';
import type {ApiResult} from '../shared/contracts';
import type {ExecutionOperation} from '../shared/executionOperation';
import {executionOperationSchema} from '../shared/executionOperation';
import {deviceUuidSchema} from '../shared/deviceRegistration';
import {parseExecutionReceipt, type ExecutionReceipt} from '../shared/executionReceipt';
import {signExecutionOperation} from './executionProofSigner';
import {configuredService} from './serviceClient';
import {z} from 'zod';

export interface ExecutionSessionOptions {
  serviceOrigin: string;
  journal: ExecutionJournal;
  vault: {read(scope: DeviceKeyScope): Promise<DeviceKeyMaterial | null>};
  transport: {requestExecution(input: unknown): Promise<ApiResult>};
}
// FAILED/KEY_MISSING describe this local attempt, never proof that a prior POST did not execute.
// Original journal records are retained for all outcomes, including historical RECORDED receipts.
export type ExecutionSessionResult =
  | {state: 'RECORDED'; receipt: ExecutionReceipt}
  | {state: 'UNKNOWN'; requestId: string}
  | {state: 'LIST'; requests: ExecutionOperation[]}
  | {state: 'SESSION_CHANGED' | 'BUSY' | 'NOT_FOUND' | 'KEY_MISSING'}
  | {state: 'FAILED'; error: 'EXECUTION_SESSION_FAILED'};
const sessionSchema = z.object({
  userId: z.string().min(1).refine(v => Array.from(v).length <= 256 && v === v.trim() &&
    !/[\x00-\x1f]/.test(v) && Array.from(v).every(c => !/^[\ud800-\udfff]$/.test(c))),
  sessionId: deviceUuidSchema,
  isCurrent: z.custom<() => boolean>(v => typeof v === 'function'),
}).strict();
const changed = Symbol('session changed');
const failed = (): ExecutionSessionResult => ({state: 'FAILED', error: 'EXECUTION_SESSION_FAILED'});

/** Main-only coordinator. Callers supply an authenticated, epoch-guarded session, never renderer identity. */
export function createExecutionSession(options: ExecutionSessionOptions) {
  const {journal, vault, transport, serviceOrigin} = options;
  if (serviceOrigin !== configuredService(serviceOrigin, {packaged: false, allowLoopbackHttp: true})) {
    throw new Error('EXECUTION_SESSION_INVALID_CONFIG');
  }
  let busy = false;
  async function run(input: DeviceIdentitySessionInput,
    operation: (context: ReturnType<typeof contextFor>) => Promise<ExecutionSessionResult>): Promise<ExecutionSessionResult> {
    let session: DeviceIdentitySessionInput;
    try {session = sessionSchema.parse(input);} catch {return failed();}
    if (busy) return {state: 'BUSY'};
    busy = true;
    const context = contextFor(session);
    try {
      context.guard();
      const result = await operation(context);
      context.guard();
      return result;
    } catch (error) {
      try {context.guard();} catch {return {state: 'SESSION_CHANGED'};}
      return error === changed ? {state: 'SESSION_CHANGED'} : failed();
    }
    finally {busy = false;}
  }
  function contextFor(session: DeviceIdentitySessionInput) {
    const scope = {serviceOrigin, userId: session.userId};
    function guard() {if (session.isCurrent() !== true) throw changed;}
    async function checked<T>(action: () => Promise<T>): Promise<T> {
      guard();
      try {const result = await action(); guard(); return result;}
      catch (error) {guard(); throw error;}
    }
    async function http(operation: string, payload: unknown): Promise<ApiResult> {
      try {return await checked(() => transport.requestExecution({operation, payload}));}
      catch (error) {
        if (error === changed) throw error;
        return {ok: false, status: 0, error: 'SERVICE_UNAVAILABLE'};
      }
    }
    function receipt(result: ApiResult, request: ExecutionOperation): ExecutionSessionResult {
      if (result.ok) {
        try {return {state: 'RECORDED', receipt: parseExecutionReceipt(result.data, request)};}
        catch { /* A bad success response cannot unlock a second operation. */ }
      }
      return {state: 'UNKNOWN', requestId: request.request_id};
    }
    async function apply(request: ExecutionOperation): Promise<ExecutionSessionResult> {
      const key = await checked(() => vault.read({...scope, deviceId: request.device_id}));
      if (!key) return {state: 'KEY_MISSING'};
      const prepared = await http('execution.prepare', {request});
      if (!prepared.ok) return {state: 'UNKNOWN', requestId: request.request_id};
      guard();
      const signed = signExecutionOperation({key, prepared: prepared.data, expected: {...scope, request}});
      return receipt(await http('execution.apply', signed), request);
    }
    async function recover(request: ExecutionOperation, retry: boolean): Promise<ExecutionSessionResult> {
      const result = await http('execution.receipt', {request_id: request.request_id});
      if (!result.ok && result.status === 404 && result.error === 'request_not_found' && retry) return apply(request);
      return receipt(result, request);
    }
    return {scope, guard, checked, apply, recover};
  }
  return {
    submit(session: DeviceIdentitySessionInput, input: unknown): Promise<ExecutionSessionResult> {
      let request: ExecutionOperation;
      try {request = executionOperationSchema.parse(input);} catch {return Promise.resolve(failed());}
      return run(session, async context => {
        const saved = await context.checked(() => journal.persist(context.scope, request));
        const original = executionOperationSchema.parse(saved.request);
        if (JSON.stringify(original) !== JSON.stringify(request)) throw new Error();
        return saved.created ? context.apply(original) : context.recover(original, false);
      });
    },
    recover(session: DeviceIdentitySessionInput, inputId: unknown, inputRetry: unknown = false): Promise<ExecutionSessionResult> {
      let requestId: string; let retry: boolean;
      try {requestId = deviceUuidSchema.parse(inputId); retry = z.boolean().parse(inputRetry);} catch {return Promise.resolve(failed());}
      return run(session, async context => {
        const saved = await context.checked(() => journal.read(context.scope, requestId));
        if (!saved) return {state: 'NOT_FOUND'};
        const request = executionOperationSchema.parse(saved);
        if (request.request_id !== requestId) throw new Error();
        return context.recover(request, retry);
      });
    },
    list(session: DeviceIdentitySessionInput): Promise<ExecutionSessionResult> {
      return run(session, async context => ({state: 'LIST', requests:
        (await context.checked(() => journal.list(context.scope))).map(r => executionOperationSchema.parse(r))}));
    },
  };
}
