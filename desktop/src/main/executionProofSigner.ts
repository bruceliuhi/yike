import {createHash, createPrivateKey, createPublicKey, sign, verify} from 'node:crypto';
import {z} from 'zod';
import type {DeviceKeyMaterial} from './deviceKeyVault';
import {executionOperationSchema, executionSignatureSchema, type ExecutionOperation} from '../shared/executionOperation';
import {deviceUuidSchema} from '../shared/deviceRegistration';

const MAX_PAYLOAD_BYTES = 16_384;
const digestSchema = z.string().length(64).regex(/^[0-9a-f]{64}$/);
const identitySchema = z.string().min(1).refine(value => Array.from(value).length <= 256);
const serviceOriginSchema = z.string().min(1).max(2048).refine(value => {
  try {
    const url = new URL(value);
    const loopback = url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
    return url.origin === value && (url.protocol === 'https:' || loopback) && !url.username && !url.password;
  } catch { return false; }
});
const expectedSchema = z.object({serviceOrigin: serviceOriginSchema, userId: identitySchema, request: executionOperationSchema}).strict();
const preparedSchema = z.object({
  signing_payload: z.string().min(2).max(MAX_PAYLOAD_BYTES),
  request_id: deviceUuidSchema,
  device_id: deviceUuidSchema,
  credential_version: z.number().int().min(1).max(2_147_483_647),
  request_sha256: digestSchema,
}).strict();
const payloadSchema = z.object({
  protocol: z.literal('yike-execution-operation-v1'),
  tenant_id: identitySchema,
  user_id: identitySchema,
  session_digest: digestSchema,
  operation: executionOperationSchema,
}).strict();

// All object keys in the validated protocol are fixed ASCII; numeric fields are bounded integers.
// This matches Python ensure_ascii=False/sort_keys=True/compact separators, not RFC 8785.
function canonicalJson(value: unknown): string {
  if (typeof value === 'string') {
    for (const character of value) {
      const point = character.codePointAt(0)!;
      if (point >= 0xd800 && point <= 0xdfff) throw new Error();
    }
    return JSON.stringify(value);
  }
  if (value === null || typeof value === 'number' && Number.isSafeInteger(value)) return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(canonicalJson).join(',') + ']';
  if (value !== null && typeof value === 'object') {
    return '{' + Object.entries(value).sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0)
      .map(([key, item]) => JSON.stringify(key) + ':' + canonicalJson(item)).join(',') + '}';
  }
  throw new Error();
}

/** Main process only: validate a server-prepared complete operation, never arbitrary sign bytes. */
export function signExecutionOperation(input: {
  readonly key: DeviceKeyMaterial;
  readonly prepared: unknown;
  readonly expected: {readonly serviceOrigin: string; readonly userId: string; readonly request: ExecutionOperation};
}): {request: ExecutionOperation; signature: string} {
  try {
    const expected = expectedSchema.parse(input.expected);
    const prepared = preparedSchema.parse(input.prepared);
    if (Buffer.byteLength(prepared.signing_payload, 'utf8') > MAX_PAYLOAD_BYTES) throw new Error();
    const payload = payloadSchema.parse(JSON.parse(prepared.signing_payload));
    // Requiring the exact canonical spelling also rejects duplicate keys, omitted nulls,
    // alternate escapes and number spellings that JSON.parse alone would silently normalize.
    if (canonicalJson(payload) !== prepared.signing_payload) throw new Error();
    const requestJson = canonicalJson(expected.request);
    if (payload.user_id !== expected.userId || canonicalJson(payload.operation) !== requestJson ||
        prepared.request_id !== expected.request.request_id || prepared.device_id !== expected.request.device_id ||
        prepared.credential_version !== expected.request.credential_version ||
        prepared.request_sha256 !== createHash('sha256').update(requestJson, 'utf8').digest('hex')) throw new Error();
    const {key} = input;
    if (key.scope.serviceOrigin !== expected.serviceOrigin || key.scope.userId !== expected.userId ||
        key.scope.deviceId !== expected.request.device_id || typeof key.privateKey !== 'string' || key.privateKey.length > 4096) throw new Error();
    const privateKey = createPrivateKey(key.privateKey);
    if (privateKey.asymmetricKeyType !== 'ed25519' || privateKey.export({format: 'pem', type: 'pkcs8'}) !== key.privateKey) throw new Error();
    const publicKey = createPublicKey(privateKey);
    if (publicKey.export({format: 'jwk'}).x !== key.publicKey) throw new Error();
    // Validation serialization is not what gets signed: preserve the server's original UTF-8 bytes.
    const bytes = Buffer.from(prepared.signing_payload, 'utf8');
    const signature = sign(null, bytes, privateKey);
    if (!verify(null, bytes, publicKey, signature)) throw new Error();
    return {request: expected.request, signature: executionSignatureSchema.parse(signature.toString('base64url'))};
  } catch { throw new Error('EXECUTION_PROOF_SIGNING_FAILED'); }
}
