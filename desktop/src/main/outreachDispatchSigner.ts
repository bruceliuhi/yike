import {createPrivateKey, createPublicKey, sign, verify} from 'node:crypto';
import {z} from 'zod';
import type {DeviceKeyMaterial} from './deviceKeyVault';
import {dispatchRequestSchema, type DispatchRequest} from './outreachDispatchProtocol';
import {executionSignatureSchema} from '../shared/executionOperation';

const MAX_PAYLOAD_BYTES = 16_384;
const identity = z.string().min(1).refine(value => Array.from(value).length <= 256);
const digest = z.string().regex(/^[0-9a-f]{64}$/);
const origin = z.string().min(1).max(2048).refine(value => {
  try {
    const url = new URL(value);
    const loopback = url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
    return url.origin === value && !url.username && !url.password && (url.protocol === 'https:' || loopback);
  } catch { return false; }
});
const expectedSchema = z.object({serviceOrigin: origin, userId: identity, tenantId: identity, request: dispatchRequestSchema}).strict();
const preparedSchema = z.object({signing_payload: z.string().min(2).max(MAX_PAYLOAD_BYTES)}).strict();
const payloadSchema = z.object({
  protocol: z.literal('yike-outreach-dispatch-v1'), tenant_id: identity, user_id: identity,
  session_digest: digest, request: dispatchRequestSchema,
}).strict();

export function canonicalJson(value: unknown): string {
  if (typeof value === 'string') {
    for (const character of value) {
      const point = character.codePointAt(0)!;
      if (point >= 0xd800 && point <= 0xdfff) throw new Error();
    }
    return JSON.stringify(value);
  }
  if (value === null || typeof value === 'boolean' || typeof value === 'number' && Number.isSafeInteger(value)) return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(canonicalJson).join(',') + ']';
  if (value !== null && typeof value === 'object') return '{' + Object.entries(value)
    .sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0)
    .map(([key, item]) => JSON.stringify(key) + ':' + canonicalJson(item)).join(',') + '}';
  throw new Error();
}

/** Private pure Ed25519 primitive shared by the two bounded signing protocols. Never exposed through IPC. */
export function signCanonicalOutreachPayload(key:DeviceKeyMaterial,expected:{serviceOrigin:string;userId:string;deviceId:string},payload:string):string {
  if(key.scope.serviceOrigin!==expected.serviceOrigin || key.scope.userId!==expected.userId || key.scope.deviceId!==expected.deviceId ||
    typeof key.privateKey!=='string' || key.privateKey.length>4096)throw new Error('OUTREACH_SIGNING_FAILED');
  const privateKey=createPrivateKey(key.privateKey);
  if(privateKey.asymmetricKeyType!=='ed25519' || privateKey.export({format:'pem',type:'pkcs8'})!==key.privateKey)throw new Error('OUTREACH_SIGNING_FAILED');
  const publicKey=createPublicKey(privateKey);
  if(publicKey.export({format:'jwk'}).x!==key.publicKey)throw new Error('OUTREACH_SIGNING_FAILED');
  const bytes=Buffer.from(payload,'utf8'),signature=sign(null,bytes,privateKey);
  if(signature.length!==64 || !verify(null,bytes,publicKey,signature))throw new Error('OUTREACH_SIGNING_FAILED');
  return executionSignatureSchema.parse(signature.toString('base64url'));
}

/** Main process only: validate and sign the server's complete canonical dispatch bytes. */
export function signOutreachDispatch(input: {
  readonly key: DeviceKeyMaterial;
  readonly prepared: unknown;
  readonly expected: {readonly serviceOrigin: string; readonly userId: string; readonly tenantId: string; readonly request: DispatchRequest};
}): {request: DispatchRequest; signature: string} {
  try {
    const expected = expectedSchema.parse(input.expected);
    const prepared = preparedSchema.parse(input.prepared);
    if (Buffer.byteLength(prepared.signing_payload, 'utf8') > MAX_PAYLOAD_BYTES) throw new Error();
    const payload = payloadSchema.parse(JSON.parse(prepared.signing_payload));
    if (canonicalJson(payload) !== prepared.signing_payload || payload.user_id !== expected.userId ||
        payload.tenant_id !== expected.tenantId || canonicalJson(payload.request) !== canonicalJson(expected.request)) throw new Error();
    return {request:expected.request,signature:signCanonicalOutreachPayload(input.key,
      {...expected,deviceId:expected.request.deviceId},prepared.signing_payload)};
  } catch { throw new Error('OUTREACH_DISPATCH_SIGNING_FAILED'); }
}
