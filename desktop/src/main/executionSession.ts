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
import {researchReservationBindingSchema,parseResearchStartReceipt,type ResearchReservationBinding,type ResearchStartReceipt} from '../shared/researchExecution';
import {researchJournalRecordSchema,type ResearchJournalRecord} from '../shared/desktopExecution';

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
  | {state:'RESEARCH_RECORDED';receipt:ResearchStartReceipt}
  | {state:'RESEARCH_LIST';requests:ResearchJournalRecord[]}
  | {state: 'SESSION_CHANGED' | 'BUSY' | 'NOT_FOUND' | 'KEY_MISSING' | 'DEVICE_NOT_READY'}
  | {state: 'FAILED'; error: 'EXECUTION_SESSION_FAILED'};
const sessionSchema = z.object({
  userId: z.string().min(1).refine(v => Array.from(v).length <= 256 && v === v.trim() &&
    !/[\x00-\x1f]/.test(v) && Array.from(v).every(c => !/^[\ud800-\udfff]$/.test(c))),
  sessionId: deviceUuidSchema,
  isCurrent: z.custom<() => boolean>(v => typeof v === 'function'),
}).strict();
const changed = Symbol('session changed');
const failed = (): ExecutionSessionResult => ({state: 'FAILED', error: 'EXECUTION_SESSION_FAILED'});
const deviceBindingSchema = z.object({deviceId: deviceUuidSchema, credentialVersion: z.number().int().min(1).max(2_147_483_647)}).strict();

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
    async function applyResearch(request:ExecutionOperation,binding:ResearchReservationBinding,authorizationToken:string):Promise<ExecutionSessionResult>{
      const key=await checked(()=>vault.read({...scope,deviceId:request.device_id}));if(!key)return {state:'KEY_MISSING'};
      const prepared=await http('execution.prepare',{request});if(!prepared.ok)return {state:'UNKNOWN',requestId:request.request_id};guard();
      const signature=signExecutionOperation({key,prepared:prepared.data,expected:{...scope,request}});
      const result=await http('researchExecution.start',{request,signature:signature.signature,authorization_token:authorizationToken});
      if(result.ok){try{return {state:'RESEARCH_RECORDED',receipt:parseResearchStartReceipt(result.data,request,binding)};}catch{/* unknown success */}}
      return {state:'UNKNOWN',requestId:request.request_id};
    }
    async function recoverResearch(record:ResearchJournalRecord):Promise<ExecutionSessionResult>{
      const result=await http('researchExecution.receipt',{request_id:record.request.request_id});
      if(result.ok){try{return {state:'RESEARCH_RECORDED',receipt:parseResearchStartReceipt(result.data,record.request,record.reservation)};}catch{/* unknown response */}}
      return {state:'UNKNOWN',requestId:record.request.request_id};
    }
    async function recover(request: ExecutionOperation, retry: boolean): Promise<ExecutionSessionResult> {
      const result = await http('execution.receipt', {request_id: request.request_id});
      if (!result.ok && result.status === 404 && result.error === 'request_not_found' && retry) return apply(request);
      return receipt(result, request);
    }
    return {scope, guard, checked, apply, recover,applyResearch,recoverResearch};
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
    recover(session: DeviceIdentitySessionInput, inputId: unknown, inputRetry: unknown = false, inputDevice?: unknown): Promise<ExecutionSessionResult> {
      let requestId: string; let retry: boolean; let device: z.infer<typeof deviceBindingSchema> | undefined;
      try {
        requestId = deviceUuidSchema.parse(inputId); retry = z.boolean().parse(inputRetry);
        device = retry ? deviceBindingSchema.parse(inputDevice) : undefined;
      } catch {return Promise.resolve(failed());}
      return run(session, async context => {
        const saved = await context.checked(() => journal.read(context.scope, requestId));
        if (!saved) return {state: 'NOT_FOUND'};
        const request = executionOperationSchema.parse(saved);
        if (request.request_id !== requestId) throw new Error();
        if (retry && (request.device_id !== device!.deviceId || request.credential_version !== device!.credentialVersion)) {
          return {state: 'DEVICE_NOT_READY'};
        }
        return context.recover(request, retry);
      });
    },
    list(session: DeviceIdentitySessionInput): Promise<ExecutionSessionResult> {
      return run(session, async context => ({state: 'LIST', requests:
        (await context.checked(() => journal.list(context.scope))).map(r => executionOperationSchema.parse(r))}));
    },
    submitResearch(session:DeviceIdentitySessionInput,inputRequest:unknown,inputBinding:unknown,inputToken:unknown):Promise<ExecutionSessionResult>{
      let request:ExecutionOperation;let reservation:ResearchReservationBinding;let authorizationToken:string;
      try{request=executionOperationSchema.refine(value=>value.operation==='START').parse(inputRequest);reservation=researchReservationBindingSchema.parse(inputBinding);
        authorizationToken=z.string().min(1).max(8192).regex(/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/).parse(inputToken);
        if(request.profile_version_id!==reservation.profile_version_id||request.strategy_version_id!==reservation.strategy_version_id||request.configuration_sha256!==reservation.configuration_sha256)throw new Error();}
      catch{return Promise.resolve(failed());}
      return run(session,async context=>{const intended=researchJournalRecordSchema.parse({record_version:2,record_type:'RESEARCH_START',request,reservation});
        if(!journal.persistResearch)throw new Error();const persistResearch=journal.persistResearch.bind(journal);
        const saved=await context.checked(()=>persistResearch(context.scope,intended));const original=researchJournalRecordSchema.parse(saved.record);
        if(JSON.stringify(original)!==JSON.stringify(intended))throw new Error();return saved.created?context.applyResearch(original.request,original.reservation,authorizationToken):context.recoverResearch(original);});
    },
    recoverResearch(session:DeviceIdentitySessionInput,inputId:unknown):Promise<ExecutionSessionResult>{let requestId:string;try{requestId=deviceUuidSchema.parse(inputId);}catch{return Promise.resolve(failed());}
      return run(session,async context=>{if(!journal.readResearch)throw new Error();const readResearch=journal.readResearch.bind(journal);
        const record=await context.checked(()=>readResearch(context.scope,requestId));if(!record)return {state:'NOT_FOUND'};
        if(record.request.request_id!==requestId)throw new Error();return context.recoverResearch(record);});},
    listResearch(session:DeviceIdentitySessionInput):Promise<ExecutionSessionResult>{return run(session,async context=>{if(!journal.listResearch)throw new Error();const listResearch=journal.listResearch.bind(journal);
      return {state:'RESEARCH_LIST',requests:(await context.checked(()=>listResearch(context.scope))).map(record=>researchJournalRecordSchema.parse(record))};});},
  };
}
