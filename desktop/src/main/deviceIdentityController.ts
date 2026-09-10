import {randomUUID} from 'node:crypto';
import {z} from 'zod';
import type {ApiResult} from '../shared/contracts';
import {deviceIdentityRetrySchema, deviceIdentityStatusSchema, type DeviceIdentityRetry, type DeviceIdentityStatus} from '../shared/deviceIdentity';
import type {DeviceIdentityResult, DeviceIdentitySessionInput} from './deviceIdentitySession';

export interface DeviceIdentityControllerOptions {
  service: {
    request(input: unknown): Promise<ApiResult>;
    requestDevice(input: unknown): Promise<ApiResult>;
    requestExecution?(input: unknown): Promise<ApiResult>;
    requestCandidate?(input: unknown): Promise<ApiResult>;
    requestConnection?(input: unknown): Promise<ApiResult>;
    requestOutreach?(input: unknown): Promise<ApiResult>;
  };
  identityFactory(transport: {requestDevice(input: unknown): Promise<ApiResult>}): {
    prepare(session: DeviceIdentitySessionInput, retry: DeviceIdentityRetry): Promise<DeviceIdentityResult>;
  };
}
export type AuthenticatedSessionResult<T> = {ok: true; value: T} |
  {ok: false; state: 'SIGNED_OUT' | 'SESSION_CHANGED' | 'BUSY' | 'FAILED'};
export type DeviceWorkerScope = {
  session: DeviceIdentitySessionInput;
  device: {deviceId: string; credentialVersion: number};
  signal?: AbortSignal;
  transport: {
    requestExecution(input: unknown): Promise<ApiResult>;
    requestCandidate(input: unknown): Promise<ApiResult>;
    requestConnection(input: unknown): Promise<ApiResult>;
    requestOutreach?(input: unknown): Promise<ApiResult>;
  };
  close(): void;
};
export type DeviceWorkerScopeResult = {ok: true; scope: DeviceWorkerScope} |
  {ok: false; state: 'SIGNED_OUT' | 'SESSION_CHANGED' | 'BUSY' | 'FAILED' | 'DEVICE_NOT_READY'};

const authenticatedSessionSchema = z.object({
  authenticated: z.literal(true),
  account_scope: z.object({id:z.string().uuid().regex(/^[a-f0-9-]+$/),version:z.literal(1)}).strict().optional(),
  user_id: z.string().min(1).refine(value => {
    if (value !== value.trim() || Array.from(value).length > 256 || /[\x00-\x1f]/.test(value)) return false;
    return Array.from(value).every(character => {
      const point = character.codePointAt(0)!;
      return point < 0xd800 || point > 0xdfff;
    });
  }),
}).strict();
const signedOutSchema = z.object({authenticated: z.literal(false)}).strict();
const failure = (): DeviceIdentityStatus => ({state: 'FAILED', error: 'DEVICE_IDENTITY_FAILED'});
const changed = (): DeviceIdentityStatus => ({state: 'SESSION_CHANGED'});

export function createDeviceIdentityController({service, identityFactory}: DeviceIdentityControllerOptions) {
  let epoch: string = randomUUID();
  let userId: string | null = null;
  let status: DeviceIdentityStatus = {state: 'NOT_PREPARED'};
  let authPending = 0;
  let preparing = false;
  let activeAuthenticatedEpoch: string | null = null;
  const workerScopes = new Set<AbortController>();
  function observe(value: DeviceIdentityStatus): DeviceIdentityStatus {
    status = {...value};
    return {...status};
  }
  function invalidate(value: DeviceIdentityStatus, expectedEpoch = epoch) {
    if (expectedEpoch !== epoch) return;
    for (const workerScope of workerScopes) workerScope.abort();
    workerScopes.clear();
    epoch = randomUUID();
    userId = null;
    observe(value);
  }
  const controller = {
    async withAuthenticatedSession<T>(action: (session: DeviceIdentitySessionInput) => Promise<T>): Promise<AuthenticatedSessionResult<T>> {
      if (preparing || authPending > 0) return {ok: false, state: 'BUSY'};
      preparing = true;
      let actionEpoch = epoch;
      const current = () => actionEpoch === epoch;
      try {
        const response = await service.request({operation: 'session.get'});
        if (!current()) return {ok: false, state: 'SESSION_CHANGED'};
        if (response.status === 401 || response.ok && signedOutSchema.safeParse(response.data).success) {
          invalidate({state: 'SIGNED_OUT'}, actionEpoch);
          return {ok: false, state: 'SIGNED_OUT'};
        }
        if (!response.ok) return {ok: false, state: 'FAILED'};
        const authenticated = authenticatedSessionSchema.safeParse(response.data);
        if (!authenticated.success) {
          invalidate(failure(), actionEpoch);
          return {ok: false, state: 'FAILED'};
        }
        if (userId !== null && userId !== authenticated.data.user_id) {
          invalidate({state: 'NOT_PREPARED'}, actionEpoch);
          actionEpoch = epoch;
        }
        userId = authenticated.data.user_id;
        activeAuthenticatedEpoch = actionEpoch;
        const value = await action({userId, sessionId: actionEpoch, isCurrent: current});
        if (!current()) return {ok: false, state: 'SESSION_CHANGED'};
        return {ok: true, value};
      } catch {return {ok: false, state: current() ? 'FAILED' : 'SESSION_CHANGED'};}
      finally {activeAuthenticatedEpoch = null; preparing = false;}
    },
    async openWorkerScope(): Promise<DeviceWorkerScopeResult> {
      // Authentication and READY capture share only the short opening mutex.
      const opened = await controller.withAuthenticatedSession(async session => {
        if (status.state !== 'READY') return null;
        const requestEpoch = session.sessionId;
        const workerScope = new AbortController();
        workerScopes.add(workerScope);
        const current = () => !workerScope.signal.aborted && requestEpoch === epoch;
        async function request(family: 'requestExecution' | 'requestCandidate' | 'requestConnection' | 'requestOutreach', input: unknown): Promise<ApiResult> {
          if (!current()) return {ok: false, status: 0, error: 'SESSION_CHANGED'};
          const send = service[family];
          if (!send) return {ok: false, status: 0, error: 'SERVICE_UNAVAILABLE'};
          try {
            const response = await send.call(service, input);
            if (!current()) return {ok: false, status: 0, error: 'SESSION_CHANGED'};
            if (response.status === 401) invalidate({state: 'SIGNED_OUT'}, requestEpoch);
            return response;
          } catch {return {ok: false, status: 0, error: current() ? 'SERVICE_UNAVAILABLE' : 'SESSION_CHANGED'};}
        }
        const scope: DeviceWorkerScope = {
          session: {...session, isCurrent: current},
          device: {deviceId: status.deviceId, credentialVersion: status.credentialVersion},
          signal: workerScope.signal,
          transport: {
            requestExecution: input => request('requestExecution', input),
            requestCandidate: input => request('requestCandidate', input),
            requestConnection: input => request('requestConnection', input),
            requestOutreach: input => request('requestOutreach', input),
          },
          close() {
            workerScope.abort();
            workerScopes.delete(workerScope);
          },
        };
        return scope;
      });
      if (!opened.ok) return opened;
      return opened.value ? {ok: true, scope: opened.value} : {ok: false, state: 'DEVICE_NOT_READY'};
    },
    async requestExecution(input: unknown): Promise<ApiResult> {
      // A stale action must not capture a newer global epoch for its next private request.
      const requestEpoch = activeAuthenticatedEpoch;
      const current = () => requestEpoch !== null && requestEpoch === epoch && activeAuthenticatedEpoch === requestEpoch;
      if (!current()) return {ok: false, status: 0, error: 'SESSION_CHANGED'};
      if (!service.requestExecution) return {ok: false, status: 0, error: 'SERVICE_UNAVAILABLE'};
      try {
        const response = await service.requestExecution(input);
        if (!current()) return {ok: false, status: 0, error: 'SESSION_CHANGED'};
        if (response.status === 401) invalidate({state: 'SIGNED_OUT'}, requestEpoch!);
        return response;
      } catch {return {ok: false, status: 0, error: current() ? 'SERVICE_UNAVAILABLE' : 'SESSION_CHANGED'};}
    },
    async requestApi(input: unknown): Promise<ApiResult> {
      let operation: unknown;
      try { operation = input && typeof input === 'object' ? (input as {operation?: unknown}).operation : undefined; }
      catch { return {ok: false, status: 0, error: 'INVALID_API_REQUEST'}; }
      const authChange = operation === 'session.login' || operation === 'session.loginPhone' || operation === 'session.logout';
      if (authChange) {
        // Invalidate on entry, not receipt: even a pending or rejected login supersedes old work.
        invalidate({state: operation === 'session.logout' ? 'SIGNED_OUT' : 'NOT_PREPARED'});
        authPending++;
      }
      const requestEpoch = epoch;
      try {
        const result = await service.request(input);
        if (result.status === 401) invalidate({state: 'SIGNED_OUT'}, requestEpoch);
        return result;
      } catch { return {ok: false, status: 0, error: 'SERVICE_UNAVAILABLE'}; }
      finally { if (authChange) authPending--; }
    },
    async prepare(input: unknown = {}): Promise<DeviceIdentityStatus> {
      let retry: DeviceIdentityRetry;
      try { retry = deviceIdentityRetrySchema.parse(input); }
      catch {
        const invalid: DeviceIdentityStatus = {state: 'INVALID_REQUEST'};
        return preparing || authPending > 0 ? invalid : observe(invalid);
      }
      if (preparing || authPending > 0) return {state: 'BUSY'};
      preparing = true;
      let prepareEpoch = epoch;
      const current = () => prepareEpoch === epoch;
      observe({state: 'NOT_PREPARED'});
      try {
        const response = await service.request({operation: 'session.get'});
        if (!current()) return changed();
        if (response.status === 401 || response.ok && signedOutSchema.safeParse(response.data).success) {
          invalidate({state: 'SIGNED_OUT'}, prepareEpoch);
          return {state: 'SIGNED_OUT'};
        }
        if (!response.ok) {
          return observe(['SERVICE_NOT_CONFIGURED', 'SERVICE_UNAVAILABLE'].includes(response.error) ? {state: 'SERVICE_UNAVAILABLE'} : failure());
        }
        const authenticated = authenticatedSessionSchema.safeParse(response.data);
        if (!authenticated.success) {
          invalidate(failure(), prepareEpoch);
          return failure();
        }
        if (userId !== null && userId !== authenticated.data.user_id) {
          invalidate({state: 'NOT_PREPARED'}, prepareEpoch);
          prepareEpoch = epoch;
        }
        userId = authenticated.data.user_id;
        // Each factory transport captures its initiating epoch, never a later global active call.
        const identity = identityFactory({async requestDevice(request) {
          if (!current()) return {ok: false, status: 0, error: 'SESSION_CHANGED'};
          try {
            const result = await service.requestDevice(request);
            if (!current()) return {ok: false, status: 0, error: 'SESSION_CHANGED'};
            if (result.status === 401) invalidate({state: 'SIGNED_OUT'}, prepareEpoch);
            return result;
          } catch (error) {
            if (!current()) return {ok: false, status: 0, error: 'SESSION_CHANGED'};
            throw error;
          }
        }});
        const result = await identity.prepare({userId, sessionId: prepareEpoch, isCurrent: current}, retry);
        if (!current()) return changed();
        const parsed = deviceIdentityStatusSchema.safeParse(result);
        return observe(parsed.success ? parsed.data : failure());
      } catch { return current() ? observe(failure()) : changed(); }
      finally { preparing = false; }
    },
    // Historical local observation only; consumers must not treat this as execution authorization.
    getStatus(): DeviceIdentityStatus {return {...status};},
  };
  return controller;
}
