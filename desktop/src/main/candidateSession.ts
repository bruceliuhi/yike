import {z} from 'zod';
import type {CandidateJournal, CandidateBatchKey} from './candidateJournal';
import type {DeviceIdentitySessionInput} from './deviceIdentitySession';
import type {DeviceKeyMaterial, DeviceKeyScope} from './deviceKeyVault';
import type {ApiResult} from '../shared/contracts';
import {candidateSubmissionSchema, type CandidateSubmission} from '../shared/candidateSubmission';
import {parseCandidateReceipt, type CandidateReceipt} from '../shared/candidateReceipt';
import {deviceUuidSchema} from '../shared/deviceRegistration';
import {signCandidateSubmission} from './candidateProofSigner';
import {configuredService} from './serviceClient';

export interface CandidateSessionOptions {
  serviceOrigin: string;
  journal: CandidateJournal;
  vault: {read(scope: DeviceKeyScope): Promise<DeviceKeyMaterial | null>};
  transport: {requestCandidate(input: unknown): Promise<ApiResult>};
}
export type CandidateSessionResult =
  | {state: 'RECORDED'; receipt: CandidateReceipt}
  | {state: 'UNKNOWN'; key: CandidateBatchKey}
  | {state: 'LIST'; keys: CandidateBatchKey[]}
  | {state: 'SESSION_CHANGED' | 'BUSY' | 'NOT_FOUND' | 'KEY_MISSING'}
  | {state: 'FAILED'; error: 'CANDIDATE_SESSION_FAILED'};
const keySchema = z.object({platformRunId: deviceUuidSchema,
  requestId: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/)}).strict();
const sessionSchema = z.object({
  userId: z.string().min(1).refine(v => Array.from(v).length <= 256 && v === v.trim() &&
    !/^[\u0085]|[\u0085]$/.test(v) && !/[\x00-\x1f]/.test(v) && Array.from(v).every(c => !/^[\ud800-\udfff]$/.test(c))),
  sessionId: deviceUuidSchema, isCurrent: z.custom<() => boolean>(v => typeof v === 'function'),
}).strict();
const changed = Symbol('session changed');
const failed = (): CandidateSessionResult => ({state: 'FAILED', error: 'CANDIDATE_SESSION_FAILED'});
const batchKey = (batch: CandidateSubmission) => keySchema.parse({platformRunId: batch.execution.platform_run_id, requestId: batch.request_id});

/** Main-only worker seam. Local failure is not proof a previous upload did not commit. */
export function createCandidateSession(options: CandidateSessionOptions) {
  const {serviceOrigin, journal, vault, transport} = options;
  if (serviceOrigin !== configuredService(serviceOrigin, {packaged: false, allowLoopbackHttp: true})) {
    throw new Error('CANDIDATE_SESSION_INVALID_CONFIG');
  }
  let busy = false;
  async function run(input: DeviceIdentitySessionInput,
    operation: (context: ReturnType<typeof contextFor>) => Promise<CandidateSessionResult>): Promise<CandidateSessionResult> {
    let session: DeviceIdentitySessionInput;
    try {session = sessionSchema.parse(input);} catch {return failed();}
    if (busy) return {state: 'BUSY'};
    busy = true; const context = contextFor(session);
    try {
      context.guard(); const result = await operation(context); context.guard(); return result;
    } catch (error) {
      try {context.guard();} catch {return {state: 'SESSION_CHANGED'};}
      return error === changed ? {state: 'SESSION_CHANGED'} : failed();
    } finally {busy = false;}
  }
  function contextFor(session: DeviceIdentitySessionInput) {
    const scope = {serviceOrigin, userId: session.userId};
    function guard() {if (session.isCurrent() !== true) throw changed;}
    async function checked<T>(action: () => Promise<T>): Promise<T> {
      guard();
      try {const result = await action(); guard(); return result;} catch (error) {guard(); throw error;}
    }
    async function http(operation: string, payload: unknown): Promise<ApiResult> {
      try {return await checked(() => transport.requestCandidate({operation, payload}));}
      catch (error) {if (error === changed) throw error; return {ok: false, status: 0, error: 'SERVICE_UNAVAILABLE'};}
    }
    function receipt(result: ApiResult, batch: CandidateSubmission): CandidateSessionResult {
      if (result.ok) {
        try {return {state: 'RECORDED', receipt: parseCandidateReceipt(result.data, batch)};} catch { /* Keep original recovery key. */ }
      }
      return {state: 'UNKNOWN', key: batchKey(batch)};
    }
    async function apply(batch: CandidateSubmission): Promise<CandidateSessionResult> {
      const key = await checked(() => vault.read({...scope, deviceId: batch.execution.device_id}));
      if (!key) return {state: 'KEY_MISSING'};
      const prepared = await http('candidate.prepare', {batch});
      if (!prepared.ok) return {state: 'UNKNOWN', key: batchKey(batch)};
      guard(); const signed = signCandidateSubmission({key, prepared: prepared.data, expected: {...scope, batch}});
      return receipt(await http('candidate.apply', signed), batch);
    }
    async function recover(batch: CandidateSubmission, retry: boolean): Promise<CandidateSessionResult> {
      const result = await http('candidate.receipt', {platform_run_id: batch.execution.platform_run_id, request_id: batch.request_id});
      if (!result.ok && result.status === 404 && result.error === 'request_not_found' && retry) return apply(batch);
      return receipt(result, batch);
    }
    return {scope, guard, checked, apply, recover};
  }
  return {
    submit(session: DeviceIdentitySessionInput, input: unknown): Promise<CandidateSessionResult> {
      let batch: CandidateSubmission;
      try {batch = candidateSubmissionSchema.parse(input); batchKey(batch);} catch {return Promise.resolve(failed());}
      return run(session, async context => {
        const saved = await context.checked(() => journal.persist(context.scope, batch));
        const original = candidateSubmissionSchema.parse(saved.batch);
        if (JSON.stringify(original) !== JSON.stringify(batch) || typeof saved.created !== 'boolean') throw new Error();
        return saved.created ? context.apply(original) : context.recover(original, false);
      });
    },
    recover(session: DeviceIdentitySessionInput, inputKey: unknown, inputRetry: unknown = false): Promise<CandidateSessionResult> {
      let key: CandidateBatchKey; let retry: boolean;
      try {key = keySchema.parse(inputKey); retry = z.boolean().parse(inputRetry);} catch {return Promise.resolve(failed());}
      return run(session, async context => {
        const saved = await context.checked(() => journal.read(context.scope, key));
        if (!saved) return {state: 'NOT_FOUND'};
        const batch = candidateSubmissionSchema.parse(saved);
        if (JSON.stringify(batchKey(batch)) !== JSON.stringify(key)) throw new Error();
        return context.recover(batch, retry);
      });
    },
    list(session: DeviceIdentitySessionInput): Promise<CandidateSessionResult> {
      return run(session, async context => ({state: 'LIST', keys: z.array(keySchema).max(1000).parse(
        await context.checked(() => journal.list(context.scope)))}));
    },
  };
}
