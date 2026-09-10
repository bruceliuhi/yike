import {createHash, createPrivateKey, createPublicKey, generateKeyPairSync, verify} from 'node:crypto';
import {describe, expect, it} from 'vitest';
import {dispatchRequestSchema, validatedOutreachDispatchOperation} from '../src/main/outreachDispatchProtocol';
import {signOutreachDispatch} from '../src/main/outreachDispatchSigner';

const requestId = '10000000-0000-4000-8000-000000000001';
const claimId = '10000000-0000-4000-8000-000000000002';
const deviceId = '10000000-0000-4000-8000-000000000003';
const resultId = '10000000-0000-4000-8000-000000000004';
const origin = 'https://pilot.example';

function claim() {
  return {action: 'CLAIM' as const, requestId, claimId, deviceId, credentialVersion: 3, contextSha256: 'a'.repeat(64)};
}

function canonical(value: any): string {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value !== null && typeof value === 'object') return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}';
  return JSON.stringify(value);
}

function fixture(request = dispatchRequestSchema.parse(claim())) {
  const pair = generateKeyPairSync('ed25519');
  const signing_payload = canonical({protocol: 'yike-outreach-dispatch-v1', tenant_id: '租户-甲\u2028乙', user_id: '用户😀', session_digest: 'b'.repeat(64), request});
  return {
    key: {scope: {serviceOrigin: origin, userId: '用户😀', deviceId}, publicKey: pair.publicKey.export({format: 'jwk'}).x!, privateKey: pair.privateKey.export({format: 'pem', type: 'pkcs8'}).toString()},
    prepared: {signing_payload},
    expected: {serviceOrigin: origin, userId: '用户😀', tenantId: '租户-甲\u2028乙', request},
  };
}

function rejected(input: Parameters<typeof signOutreachDispatch>[0]) {
  let caught: unknown;
  try { signOutreachDispatch(input); } catch (error) { caught = error; }
  expect(caught).toBeInstanceOf(Error);
  expect((caught as Error).message).toBe('OUTREACH_DISPATCH_SIGNING_FAILED');
  expect((caught as Error).cause).toBeUndefined();
}

describe('outreach dispatch request and private routes', () => {
  it('expands Python model_dump nulls for CLAIM and rejects noncanonical UUIDs/extra fields', () => {
    expect(dispatchRequestSchema.parse(claim())).toEqual({...claim(), resultId: null, outcome: null});
    expect(dispatchRequestSchema.safeParse({...claim(), requestId: 'A0000000-0000-4000-8000-000000000001'}).success).toBe(false);
    expect(dispatchRequestSchema.safeParse({...claim(), extra: true}).success).toBe(false);
    expect(dispatchRequestSchema.safeParse({...claim(), outcome: {status: 'UNKNOWN'}}).success).toBe(false);
  });

  it('matches RESULT outcome invariants, strict booleans, opaque receipt id and aware time', () => {
    const sent = {...claim(), action: 'RESULT', resultId, outcome: {status: 'SENT', confirmed: true,
      proof: {kind: 'ACCEPTED', externalId: 'receipt:1', sha256: 'c'.repeat(64), observedAt: '2026-09-10T12:34:56+08:00'}}};
    expect(dispatchRequestSchema.parse(sent).outcome).toEqual({...sent.outcome, confirmedNotDelivered: null});
    expect(dispatchRequestSchema.safeParse({...sent, outcome: {...sent.outcome, confirmed: 1}}).success).toBe(false);
    expect(dispatchRequestSchema.safeParse({...sent, outcome: {...sent.outcome, proof: {...sent.outcome.proof, externalId: '../secret'}}}).success).toBe(false);
    expect(dispatchRequestSchema.safeParse({...sent, outcome: {...sent.outcome, proof: {...sent.outcome.proof, observedAt: '2026-09-10T12:34:56'}}}).success).toBe(false);
    expect(dispatchRequestSchema.safeParse({...sent, outcome: {...sent.outcome, confirmedNotDelivered: true}}).success).toBe(false);
    expect(dispatchRequestSchema.safeParse({...claim(), action: 'RESULT', resultId, outcome: {status: 'UNKNOWN'}}).success).toBe(true);
  });

  it.each([
    [{operation: 'outreach.dispatch.prepare', payload: {request: claim()}}, '/api/ui/outreach/dispatch/signing-payload', 'POST'],
    [{operation: 'outreach.dispatch.apply', payload: {request: claim(), signature: 'A'.repeat(86)}}, '/api/ui/outreach/dispatch', 'POST'],
    [{operation: 'outreach.dispatch.receipt', payload: {requestId}}, `/api/ui/outreach/queue/${requestId}`, 'GET'],
  ] as const)('maps only fixed private operation %#', (input, path, method) => {
    const routed = validatedOutreachDispatchOperation(input);
    const payload = input.operation === 'outreach.dispatch.receipt' ? input.payload : {
      ...input.payload, request: dispatchRequestSchema.parse(input.payload.request),
    };
    expect(routed).toEqual({path, method, logout: false, ...(method === 'POST' ? {body: JSON.stringify(payload)} : {})});
  });

  it.each([
    {operation: 'outreach.dispatch.receipt', payload: {requestId: '../admin'}},
    {operation: 'outreach.dispatch.receipt', payload: {requestId}, path: '/api/admin'},
    {operation: 'outreach.dispatch.prepare', payload: {request: claim(), signature: 'A'.repeat(86)}},
    {operation: 'outreach.dispatch.cancel', payload: {requestId}},
  ])('rejects unknown, injected, or arbitrary paths %#', input => {
    expect(validatedOutreachDispatchOperation(input)).toBeNull();
  });
});

describe('main-only outreach dispatch signer', () => {
  it('signs the original canonical Python UTF-8 bytes with expanded nulls', () => {
    const input = fixture();
    // Generated with Python 3.12 from DispatchRequest.model_validate/model_dump
    // and pilot.outreach_dispatch.signing_payload (not a TypeScript serializer).
    expect(createHash('sha256').update(input.prepared.signing_payload, 'utf8').digest('hex'))
      .toBe('e635edfb9f1120abd1c8ed038496e722ecb20ae1a0b50d125e9469c1c250ea56');
    expect(input.prepared.signing_payload).toContain('"outcome":null');
    expect(input.prepared.signing_payload).toContain('"resultId":null');
    const original = structuredClone(input);
    const signed = signOutreachDispatch(input);
    expect(signed.request).toEqual(input.expected.request);
    expect(verify(null, Buffer.from(input.prepared.signing_payload), createPublicKey(input.key.privateKey), Buffer.from(signed.signature, 'base64url'))).toBe(true);
    expect(input).toEqual(original);
    expect(signOutreachDispatch(input)).toEqual(signed);
  });

  it.each([
    (input: ReturnType<typeof fixture>) => { input.expected.tenantId = 'other'; },
    (input: ReturnType<typeof fixture>) => { input.expected.request.claimId = '10000000-0000-4000-8000-000000000099'; },
    (input: ReturnType<typeof fixture>) => { input.prepared.signing_payload += '\n'; },
    (input: ReturnType<typeof fixture>) => { input.prepared.signing_payload = input.prepared.signing_payload.replace('"protocol":', '"protocol":"bad","protocol":'); },
    (input: ReturnType<typeof fixture>) => { input.prepared.signing_payload = input.prepared.signing_payload.replace('"outcome":null,', ''); },
    (input: ReturnType<typeof fixture>) => { input.key.scope.serviceOrigin = 'https://other.example'; },
    (input: ReturnType<typeof fixture>) => { input.key.privateKey = fixture().key.privateKey; },
  ])('rejects altered identity, request, canonical bytes, scope, or key %#', mutate => {
    const input = fixture(); mutate(input); rejected(input);
  });

  it('rejects non-Ed25519 and arbitrary signing material with a fixed error', () => {
    const input = fixture();
    const pair = generateKeyPairSync('ec', {namedCurve: 'prime256v1'});
    input.key.privateKey = pair.privateKey.export({format: 'pem', type: 'pkcs8'}).toString();
    rejected(input);
    rejected({...fixture(), prepared: {signing_payload: '/private/secret'}});
    expect(createPrivateKey(fixture().key.privateKey).asymmetricKeyType).toBe('ed25519');
  });
});
