import {createHash, createPrivateKey, createPublicKey, sign, verify} from 'node:crypto';
import {z} from 'zod';
import type {DeviceKeyMaterial} from './deviceKeyVault';
import {candidateSubmissionSchema, type CandidateSubmission} from '../shared/candidateSubmission';

const MAX_PAYLOAD_BYTES = 16_384;
const opaque = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/);
const digest = z.string().regex(/^[0-9a-f]{64}$/);
const identity = z.string().min(1).refine(value => Array.from(value).length <= 256);
const origin = z.string().min(1).max(2048).refine(value => {
  try {
    const url = new URL(value);
    return url.origin === value && !url.username && !url.password && (url.protocol === 'https:' ||
      url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname));
  } catch {return false;}
});
const expectedSchema = z.object({serviceOrigin: origin, userId: identity, batch: candidateSubmissionSchema}).strict();
const preparedSchema = z.object({signing_payload: z.string().min(2).max(MAX_PAYLOAD_BYTES), request_id: opaque, device_id: opaque,
  credential_version: z.number().int().min(1).max(2_147_483_647), batch_fingerprint: digest}).strict();
const payloadSchema = z.object({protocol: z.literal('yike-candidate-submission-v1'), tenant_id: identity, user_id: identity,
  session_digest: digest, request_id: opaque, batch_fingerprint: digest}).strict();

// Fixed ASCII model keys, booleans and bounded integers: Python ensure_ascii=False, sorted compact JSON.
// Deliberately not NFC normalization or RFC 8785; original codepoints and record order matter.
function canonicalJson(value: unknown): string {
  if (typeof value === 'string') {
    for (const character of value) {const point = character.codePointAt(0)!; if (point >= 0xd800 && point <= 0xdfff) throw new Error();}
    return JSON.stringify(value);
  }
  if (value === null || typeof value === 'boolean' || typeof value === 'number' && Number.isSafeInteger(value)) return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(canonicalJson).join(',') + ']';
  if (typeof value === 'object' && value !== null) return '{' + Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)
    .map(([key, item]) => JSON.stringify(key) + ':' + canonicalJson(item)).join(',') + '}';
  throw new Error();
}

/** Main-only complete candidate proof; never an arbitrary-byte signing primitive. */
export function signCandidateSubmission(input: {
  readonly key: DeviceKeyMaterial;
  readonly prepared: unknown;
  readonly expected: {readonly serviceOrigin: string; readonly userId: string; readonly batch: CandidateSubmission};
}): {batch: CandidateSubmission; signature: string} {
  try {
    const expected = expectedSchema.parse(input.expected);
    const prepared = preparedSchema.parse(input.prepared);
    if (Buffer.byteLength(prepared.signing_payload, 'utf8') > MAX_PAYLOAD_BYTES) throw new Error();
    const payload = payloadSchema.parse(JSON.parse(prepared.signing_payload));
    // Exact spelling rejects duplicate keys, extra fields, reordered keys and alternate escapes.
    if (canonicalJson(payload) !== prepared.signing_payload) throw new Error();
    const {request_id, ...fingerprinted} = expected.batch;
    const fingerprint = createHash('sha256').update(canonicalJson(fingerprinted), 'utf8').digest('hex');
    const execution = expected.batch.execution;
    if (payload.user_id !== expected.userId || payload.request_id !== request_id || prepared.request_id !== request_id ||
      payload.batch_fingerprint !== fingerprint || prepared.batch_fingerprint !== fingerprint || prepared.device_id !== execution.device_id ||
      prepared.credential_version !== execution.credential_version) throw new Error();
    const {key} = input;
    if (key.scope.serviceOrigin !== expected.serviceOrigin || key.scope.userId !== expected.userId || key.scope.deviceId !== execution.device_id ||
      typeof key.privateKey !== 'string' || key.privateKey.length > 4096) throw new Error();
    const privateKey = createPrivateKey(key.privateKey);
    if (privateKey.asymmetricKeyType !== 'ed25519' || privateKey.export({format: 'pem', type: 'pkcs8'}) !== key.privateKey) throw new Error();
    const publicKey = createPublicKey(privateKey);
    if (publicKey.export({format: 'jwk'}).x !== key.publicKey) throw new Error();
    const bytes = Buffer.from(prepared.signing_payload, 'utf8');
    const signature = sign(null, bytes, privateKey);
    if (signature.length !== 64 || !verify(null, bytes, publicKey, signature)) throw new Error();
    return {batch: expected.batch, signature: signature.toString('base64url')};
  } catch {throw new Error('CANDIDATE_PROOF_SIGNING_FAILED');}
}
