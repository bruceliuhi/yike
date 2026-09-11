import type {ApiResult} from '../shared/contracts';
import {validatedOperation, type ServiceOperation} from './servicePolicy';
import {validatedDeviceOperation} from './deviceServicePolicy';
import {validatedExecutionOperation} from './executionServicePolicy';
import {validatedCandidateOperation} from './candidateServicePolicy';
import {validatedConnectionOperation} from './connectionServicePolicy';
import {validatedOutreachDispatchOperation} from './outreachDispatchProtocol';
import {validatedOutreachConfirmationOperation} from './outreachConfirmationProtocol';
import {validatedNativeReplyOperation} from './nativeReplyProtocol';

export function configuredService(
  input: string | undefined,
  environment: {packaged: boolean; allowLoopbackHttp: boolean}
): string | null {
  if (!input || /[\x00-\x20\x7f\\]/.test(input)) return null;
  try {
    const url = new URL(input);
    if (url.username || url.password || url.search || url.hash || url.pathname !== '/') return null;
    const loopbackHttp = !environment.packaged && environment.allowLoopbackHttp &&
      ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) && url.protocol === 'http:';
    return url.protocol === 'https:' || loopbackHttp ? url.origin : null;
  } catch { return null; }
}

type Fetcher = (url: string, options: RequestInit) => Promise<Response>;
interface ServiceClientOptions {
  baseUrl: string | null;
  fetch: Fetcher;
  clearSession: () => Promise<void>;
  beforeAuthentication?: () => Promise<void>;
  persistSession?: () => Promise<void>;
  timeoutMs?: number;
  maxResponseBytes?: number;
}

async function boundedJson(response: Response, limit: number): Promise<unknown> {
  if (Number(response.headers.get('content-length')) > limit) {
    await response.body?.cancel();
    throw new Error('SERVICE_RESPONSE_TOO_LARGE');
  }
  if (response.headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'application/json') {
    await response.body?.cancel();
    throw new Error('SERVICE_NON_JSON_RESPONSE');
  }
  if (!response.body) throw new Error('SERVICE_INVALID_RESPONSE');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let bytes = 0;
  let text = '';
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > limit) {
        await reader.cancel();
        throw new Error('SERVICE_RESPONSE_TOO_LARGE');
      }
      text += decoder.decode(value, {stream: true});
    }
    text += decoder.decode();
    return JSON.parse(text);
  } catch (error) {
    if (error instanceof Error && error.message === 'SERVICE_RESPONSE_TOO_LARGE') throw error;
    throw new Error('SERVICE_INVALID_RESPONSE');
  } finally { reader.releaseLock(); }
}

function responseError(data: unknown, status: number): string {
  if (data && typeof data === 'object' && 'detail' in data) {
    const detail = data.detail;
    if (detail && typeof detail === 'object' && 'code' in detail &&
      typeof detail.code === 'string' && /^[a-z][a-z0-9_]{0,63}$/.test(detail.code)) return detail.code;
  }
  return `HTTP_${status}`;
}

export function createServiceClient(options: ServiceClientOptions): {
  request(input: unknown): Promise<ApiResult>;
  requestDevice(input: unknown): Promise<ApiResult>;
  requestExecution(input: unknown): Promise<ApiResult>;
  requestCandidate(input: unknown): Promise<ApiResult>;
  requestConnection(input: unknown): Promise<ApiResult>;
  requestOutreach(input: unknown): Promise<ApiResult>;
} {
  let queue: Promise<unknown> = Promise.resolve();
  let pending = 0;
  async function execute(operation: ServiceOperation): Promise<ApiResult> {
    if (options.baseUrl === null) return {ok: false, status: 0, error: 'SERVICE_NOT_CONFIGURED'};
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), options.timeoutMs ?? operation.timeoutMs ?? 12_000);
    const authenticating=operation.method==='POST'&&[
      '/api/ui/session','/api/ui/auth/sms-session','/api/ui/auth/access-session',
    ].includes(operation.path);
    try {
      if(authenticating&&options.beforeAuthentication){
        try{await options.beforeAuthentication();}catch{return {ok:false,status:0,error:'SESSION_CLEAR_FAILED'};}
      }
      const response = await options.fetch(options.baseUrl + operation.path, {
        method: operation.method,
        headers: {
          Accept: 'application/json',
          Origin: options.baseUrl,
          ...(operation.body !== undefined ? {'Content-Type': 'application/json'} : {})
        },
        body: operation.body,
        credentials: 'include', redirect: 'manual', cache: 'no-store', signal: abort.signal
      });
      if (response.status >= 300 && response.status < 400 || response.redirected) {
        await response.body?.cancel();
        return {ok: false, status: response.status, error: 'SERVICE_REDIRECT_REJECTED'};
      }
      const data = await boundedJson(response, options.maxResponseBytes ?? 2_097_152);
      if(response.ok&&authenticating&&options.persistSession){
        try{
          if(!data||typeof data!=='object'||!('authenticated' in data)||data.authenticated!==true||
            !('user_id' in data)||typeof data.user_id!=='string'||!data.user_id.trim())throw new Error();
          await options.persistSession();
        }catch{
          try{await options.clearSession();}catch{return {ok:false,status:0,error:'SESSION_CLEAR_FAILED'};}
          return {ok:false,status:0,error:'SESSION_PERSIST_FAILED'};
        }
      }
      return response.ok ? {ok: true, status: response.status, data} : {
        ok: false, status: response.status, error: responseError(data, response.status)
      };
    } catch (error) {
      const code = abort.signal.aborted ? 'SERVICE_TIMEOUT' : error instanceof Error &&
        ['SERVICE_RESPONSE_TOO_LARGE', 'SERVICE_NON_JSON_RESPONSE', 'SERVICE_INVALID_RESPONSE'].includes(error.message)
        ? error.message : 'SERVICE_UNAVAILABLE';
      return {ok: false, status: 0, error: code};
    } finally {
      clearTimeout(timeout);
      if (operation.logout) {
        try { await options.clearSession(); }
        catch { return {ok: false, status: 0, error: 'SESSION_CLEAR_FAILED'}; }
      }
    }
  }
  function enqueue(operation: ServiceOperation | null): Promise<ApiResult> {
    if (!operation) return Promise.resolve({ok: false, status: 0, error: 'INVALID_API_REQUEST'});
    if (pending >= 16) return Promise.resolve({ok: false, status: 0, error: 'SERVICE_BUSY'});
    pending++;
    // Public session changes and all private channels share cookie ordering and capacity.
    const result = queue.then(() => execute(operation)).finally(() => { pending--; });
    queue = result.catch(() => undefined);
    return result;
  }
  return {
    request(input) { return enqueue(validatedOperation(input)); },
    requestDevice(input) { return enqueue(validatedDeviceOperation(input)); },
    requestExecution(input) { return enqueue(validatedExecutionOperation(input)); },
    requestCandidate(input) { return enqueue(validatedCandidateOperation(input)); },
    requestConnection(input) { return enqueue(validatedConnectionOperation(input)); },
    requestOutreach(input) { return enqueue(validatedOutreachDispatchOperation(input) ?? validatedOutreachConfirmationOperation(input) ?? validatedNativeReplyOperation(input)); },
  };
}
