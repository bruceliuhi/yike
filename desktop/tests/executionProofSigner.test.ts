import {createHash, createPublicKey, generateKeyPairSync, verify} from 'node:crypto';
import {describe, expect, it} from 'vitest';
import {signExecutionOperation} from '../src/main/executionProofSigner';
import {executionOperationSchema, executionSignatureSchema} from '../src/shared/executionOperation';

const origin = 'https://pilot.example';
const userId = '用户-甲😀';
const failure = 'EXECUTION_PROOF_SIGNING_FAILED';
// Generated with Python 3.11, the actual ExecutionOperation model and the pure
// _json/execution_signing_payload AST functions from pilot/execution_runtime.py.
// Isolating those pure functions avoids requiring the database/libsodium runtime.
const pythonRequestDigest = '0c0cf7235fa1ea61c1c48053bbef3765148d5403277ab1907fe14399b131054f';
const pythonPayloadDigest = '157b61bdcbb1195895a9cc6838d0f8f545532c68278d7c81c68d68665b0cb715';
const pythonPayload = '{"operation":{"configuration_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","credential_version":3,"device_id":"00000000-0000-0000-0000-000000000002","execution_generation":null,"lease_id":null,"operation":"START","platform_run_id":null,"profile_version_id":"profile-1","request_id":"00000000-0000-0000-0000-000000000001","schema_version":"execution-runtime-v1","strategy_version_id":"strategy-1","targets":[{"access_mode":"PUBLIC_ANONYMOUS","connection_id":null,"connection_version":null,"platform":"PUBLIC_WEB"},{"access_mode":"PLATFORM_ACCOUNT","connection_id":"00000000-0000-0000-0000-000000000003","connection_version":2,"platform":"DOUYIN"}],"task_id":null},"protocol":"yike-execution-operation-v1","session_digest":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","tenant_id":"租户-甲\u2028乙","user_id":"用户-甲😀"}';

// Test mutation helper only; positive cross-language evidence uses the frozen Python bytes.
function sortedJson(value: any): string {
  if (Array.isArray(value)) return '[' + value.map(sortedJson).join(',') + ']';
  if (value !== null && typeof value === 'object') return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + sortedJson(value[key])).join(',') + '}';
  return JSON.stringify(value);
}
function fixture() {
  const pair = generateKeyPairSync('ed25519');
  const request = JSON.parse(pythonPayload).operation;
  return {
    key: {scope: {serviceOrigin: origin, userId, deviceId: request.device_id}, publicKey: pair.publicKey.export({format: 'jwk'}).x!, privateKey: pair.privateKey.export({format: 'pem', type: 'pkcs8'}).toString()},
    prepared: {signing_payload: pythonPayload, request_id: request.request_id, device_id: request.device_id, credential_version: request.credential_version, request_sha256: pythonRequestDigest},
    expected: {serviceOrigin: origin, userId, request},
  };
}
function rejected(input: Parameters<typeof signExecutionOperation>[0]) {
  let caught: unknown;
  try {signExecutionOperation(input);} catch (error) {caught = error;}
  expect(caught).toBeInstanceOf(Error);
  expect((caught as Error).message).toBe(failure);
  expect((caught as Error).cause).toBeUndefined();
}

describe('main-only complete execution operation signer', () => {
  it('signs the original Python UTF-8 bytes including emoji, U+2028, nulls and target order', () => {
    const input = fixture();
    expect(createHash('sha256').update(pythonPayload, 'utf8').digest('hex')).toBe(pythonPayloadDigest);
    const original = structuredClone(input);
    const signed = signExecutionOperation(input);
    expect(Object.keys(signed).sort()).toEqual(['request', 'signature']);
    expect(signed.request).toEqual(executionOperationSchema.parse(input.expected.request));
    expect(executionSignatureSchema.safeParse(signed.signature).success).toBe(true);
    const signature = Buffer.from(signed.signature, 'base64url');
    expect(signature).toHaveLength(64);
    expect(signature.toString('base64url')).toBe(signed.signature);
    expect(verify(null, Buffer.from(pythonPayload, 'utf8'), createPublicKey(input.key.privateKey), signature)).toBe(true);
    expect(verify(null, Buffer.from(pythonPayload + '\n', 'utf8'), createPublicKey(input.key.privateKey), signature)).toBe(false);
    expect(input).toEqual(original);
    expect(signExecutionOperation(input)).toEqual(signed);
    input.expected.request.targets.reverse();
    expect(signed.request.targets?.[0].platform).toBe('PUBLIC_WEB');
  });

  it.each(['CLAIM', 'RENEW', 'CANCEL'] as const)('signs a fully bound %s operation without START fields', operation => {
    const input = fixture();
    const request = {...input.expected.request, operation, profile_version_id: null, strategy_version_id: null, configuration_sha256: null, targets: null,
      task_id: 'task-1', platform_run_id: operation === 'CANCEL' ? null : 'platform-run-1', lease_id: operation === 'RENEW' ? 'lease-1' : null, execution_generation: operation === 'RENEW' ? 2 : null};
    const payload = {...JSON.parse(pythonPayload), operation: request};
    input.expected.request = request;
    input.prepared.signing_payload = sortedJson(payload);
    input.prepared.request_sha256 = createHash('sha256').update(sortedJson(request)).digest('hex');
    const result = signExecutionOperation(input);
    expect(result.request).toEqual(request);
    expect(verify(null, Buffer.from(input.prepared.signing_payload), createPublicKey(input.key.privateKey), Buffer.from(result.signature, 'base64url'))).toBe(true);
  });

  it('accepts a new server session digest as different bytes, without fabricating tenant/session authority', () => {
    const input = fixture(); const first = signExecutionOperation(input);
    input.prepared.signing_payload = sortedJson({...JSON.parse(pythonPayload), session_digest: 'c'.repeat(64)});
    const second = signExecutionOperation(input);
    expect(second.signature).not.toBe(first.signature);
    expect(input.prepared.request_sha256).toBe(pythonRequestDigest);
  });

  it.each([
    {request_id: '00000000-0000-0000-0000-000000000099'}, {device_id: '00000000-0000-0000-0000-000000000099'},
    {credential_version: 4}, {credential_version: '3'}, {request_sha256: 'f'.repeat(64)}, {request_sha256: pythonRequestDigest.toUpperCase()},
    {privateKey: 'secret'}, {tenant_id: 'injected'}, {signing_payload: {}},
  ])('rejects changed or additional preparation envelope fields %#', change => {
    const input = fixture(); rejected({...input, prepared: {...input.prepared, ...change}});
  });

  it.each(['request_id', 'device_id', 'credential_version', 'request_sha256', 'signing_payload'])('requires preparation envelope field %s', field => {
    const input = fixture(); delete (input.prepared as Record<string, unknown>)[field]; rejected(input);
  });

  it.each([
    {protocol: 'yike-device-proof-v1'}, {user_id: 'other-owner'}, {user_id: null}, {tenant_id: ''}, {tenant_id: '\ud800'},
    {session_digest: 'session-a'}, {session_digest: 'B'.repeat(64)}, {session_digest: null}, {signature: 'extra'},
  ])('rejects changed domain/user, invalid server identity/digest, or extra payload fields %#', change => {
    const input = fixture(); input.prepared.signing_payload = sortedJson({...JSON.parse(pythonPayload), ...change}); rejected(input);
  });

  it.each(['protocol', 'tenant_id', 'user_id', 'session_digest', 'operation'])('requires payload field %s', field => {
    const input = fixture(); const payload = JSON.parse(pythonPayload); delete payload[field]; input.prepared.signing_payload = sortedJson(payload); rejected(input);
  });

  it.each([
    (value: any) => {value.operation.request_id = '00000000-0000-0000-0000-000000000099';},
    (value: any) => {value.operation.targets.reverse();},
    (value: any) => {delete value.operation.task_id;},
    (value: any) => {value.operation.credential_version = 4;},
    (value: any) => {value.operation.targets[1].connection_version = 3;},
    (value: any) => {value.operation.configuration_sha256 = 'd'.repeat(64);},
  ])('binds the complete expected operation including null fields and targets order %#', mutate => {
    const input = fixture(); const payload = JSON.parse(pythonPayload); mutate(payload);
    input.prepared.signing_payload = sortedJson(payload);
    // Even a self-consistent changed response digest cannot replace the trusted expected request.
    input.prepared.request_sha256 = createHash('sha256').update(sortedJson(payload.operation)).digest('hex');
    rejected(input);
  });

  it('does not confuse request_sha256 with the database hash excluding request_id', () => {
    const input = fixture(); const request = {...input.expected.request}; delete request.request_id;
    input.prepared.request_sha256 = createHash('sha256').update(sortedJson(request)).digest('hex'); rejected(input);
  });

  it.each([
    (payload: string) => payload + '\n',
    (payload: string) => JSON.stringify(JSON.parse(payload), null, 2),
    (payload: string) => payload.replace('"protocol":', '"protocol":"wrong","protocol":'),
    (payload: string) => payload.replace('"credential_version":3', '"credential_version":3,"credential_version":3'),
    (payload: string) => payload.replace('"credential_version":3', '"credential_version":3.0'),
    (payload: string) => payload.replace('租', '\\u79df'),
    (payload: string) => payload.replace('"operation":{', '"zzz":0,"operation":{'),
  ])('rejects noncanonical or duplicate-key original JSON %#', mutate => {
    const input = fixture(); input.prepared.signing_payload = mutate(pythonPayload); rejected(input);
  });

  it.each(['serviceOrigin', 'userId', 'deviceId'] as const)('rejects wrong key %s scope', field => {
    const input = fixture(); input.key.scope[field] = field === 'serviceOrigin' ? 'https://other.example' : 'wrong'; rejected(input);
  });

  it.each(['https://pilot.example/path', 'http://untrusted.example', 'https://pilot.example/'])('rejects a noncanonical trusted service origin %s', serviceOrigin => {
    const input = fixture(); input.expected.serviceOrigin = serviceOrigin; input.key.scope.serviceOrigin = serviceOrigin; rejected(input);
  });

  it('rejects a different private key even when the claimed public key matches', () => {
    const input = fixture(); input.key.privateKey = fixture().key.privateKey; rejected(input);
  });
  it('rejects non-Ed25519 private keys', () => {
    const input = fixture(); const pair = generateKeyPairSync('ec', {namedCurve: 'prime256v1'});
    input.key.privateKey = pair.privateKey.export({format: 'pem', type: 'pkcs8'}).toString(); rejected(input);
  });
  it('rejects noncanonical PEM and never exposes underlying crypto diagnostics', () => {
    const input = fixture(); input.key.privateKey += '\n'; rejected(input);
    input.key.privateKey = '/private/key/TEST-secret-material'; rejected(input);
  });
  it('does not accept arbitrary signing bytes in place of the preparation envelope', () => {
    const input = fixture(); rejected({...input, prepared: pythonPayload});
  });
});
