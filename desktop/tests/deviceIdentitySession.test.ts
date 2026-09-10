import {createPublicKey, generateKeyPairSync, randomUUID, verify} from 'node:crypto';
import {describe, expect, it} from 'vitest';
import {createDeviceIdentitySession, type DeviceIdentitySessionInput, type DeviceIdentitySessionOptions} from '../src/main/deviceIdentitySession';
import type {DeviceIdentityRecord, DeviceIdentityJournal} from '../src/main/deviceIdentityJournal';
import type {DeviceKeyMaterial} from '../src/main/deviceKeyVault';
import type {DeviceChallengeRequest, DeviceProofReceipt} from '../src/shared/deviceProof';
import type {ApiResult} from '../src/shared/contracts';

const origin = 'https://pilot.example';
const userId = 'TEST-owner';
const deviceId = '12345678-1234-4234-8234-123456789abc';
const now = 1_789_000_000;
const succeeded = {state: 'READY', deviceId, credentialVersion: 1};
const ok = (data: unknown): ApiResult => ({ok: true, status: 200, data});
const missing = (): ApiResult => ({ok: false, status: 404, error: 'request_not_found'});
const unavailable = (): ApiResult => ({ok: false, status: 0, error: 'SERVICE_UNAVAILABLE'});

function fixture() {
  const pair = generateKeyPairSync('ed25519');
  const key: DeviceKeyMaterial = {
    scope: {serviceOrigin: origin, userId, deviceId},
    publicKey: pair.publicKey.export({format: 'jwk'}).x!,
    privateKey: pair.privateKey.export({format: 'pem', type: 'pkcs8'}).toString(),
  };
  const state = {
    record: null as DeviceIdentityRecord | null,
    registration: null as Record<string, unknown> | null,
    key: key as DeviceKeyMaterial | null,
    identity: {device_id: deviceId, device_status: 'ACTIVE', credential_version: 0, public_key: null as string | null},
    current: true,
    events: [] as string[],
    calls: [] as {operation: string; payload: Record<string, any>}[],
    receipts: new Map<string, DeviceProofReceipt>(),
    challenges: new Map<string, {request: DeviceChallengeRequest; envelope: {request_id: string; challenge_id: string; signing_payload: string; expires_at: number}}>(),
    after: async (_event: string): Promise<void> => {},
    override: (_operation: string, _payload: Record<string, any>): ApiResult | undefined => undefined,
    lost: new Set<string>(),
  };
  async function finish<T>(event: string, value: T): Promise<T> {
    state.events.push(event);
    await state.after(event);
    return structuredClone(value);
  }
  const journal: DeviceIdentityJournal = {
    async read() {return finish('journal.read', state.record);},
    async loadOrCreate(scope, device_label) {
      const created = state.record === null;
      state.record ??= {version: 1, scope: {...scope}, registration: {request_id: randomUUID(), device_label}, proof: null};
      return finish('journal.load', {record: state.record, created});
    },
    async setProof(_scope, registrationId, expectedProofId, proof) {
      if (!state.record || state.record.registration.request_id !== registrationId ||
          (state.record.proof?.request.request_id ?? null) !== expectedProofId) throw new Error('private CAS detail');
      state.record = {...state.record, proof: structuredClone(proof)};
      return finish('journal.proof', state.record);
    },
  };
  const vault = {
    async read() {return finish('vault.read', state.key);},
    async getOrCreate() {
      state.key ??= key;
      return finish('vault.create', state.key);
    },
  };
  const transport = {async requestDevice(input: unknown): Promise<ApiResult> {
    const {operation, payload} = input as {operation: string; payload: Record<string, any>};
    state.calls.push(structuredClone({operation, payload}));
    const overridden = state.override(operation, payload);
    let result: ApiResult;
    if (overridden) result = overridden;
    else switch (operation) {
      case 'devices.register':
        state.registration ??= {...payload, device_id: deviceId, state: 'SUCCEEDED', registered_at: '2026-09-10T12:00:00Z'};
        result = ok(state.registration); break;
      case 'devices.registration': result = state.registration ? ok(state.registration) : missing(); break;
      case 'devices.identity': result = ok(state.identity); break;
      case 'devices.receipt': result = state.receipts.has(payload.request_id) ? ok(state.receipts.get(payload.request_id)) : missing(); break;
      case 'devices.challenge': {
        const request = payload.request as DeviceChallengeRequest;
        let found = state.challenges.get(request.request_id);
        if (!found) {
          const challengeId = randomUUID();
          const signingPayload = {
            challenge_id: challengeId, device_id: deviceId,
            expected_credential_version: request.expected_credential_version, expires_at: now + 120,
            nonce: Buffer.alloc(32, 7).toString('base64url'), operation: request.operation,
            protocol: 'yike-device-proof-v1', request_id: request.request_id,
            session_digest: 'a'.repeat(64), target_public_key: request.public_key ?? state.identity.public_key,
            tenant_id: 'TEST-tenant', user_id: userId,
          };
          found = {request: structuredClone(request), envelope: {request_id: request.request_id, challenge_id: challengeId, signing_payload: JSON.stringify(signingPayload), expires_at: now + 120}};
          state.challenges.set(request.request_id, found);
          state.receipts.set(request.request_id, {request_id: request.request_id, device_id: deviceId, operation: request.operation, state: 'PENDING', credential_version: null});
        }
        result = ok(found.envelope); break;
      }
      case 'devices.complete': {
        const found = [...state.challenges.values()].find(item => item.envelope.challenge_id === payload.challenge_id)!;
        expect(verify(null, Buffer.from(found.envelope.signing_payload), createPublicKey(key.privateKey), Buffer.from(payload.proof.signature, 'base64url'))).toBe(true);
        expect(payload.proof.previous_signature).toBeNull();
        state.identity.credential_version = found.request.operation === 'BIND' ? 1 : found.request.expected_credential_version;
        state.identity.public_key = key.publicKey;
        const receipt: DeviceProofReceipt = {request_id: found.request.request_id, device_id: deviceId, operation: found.request.operation, state: 'SUCCEEDED', credential_version: state.identity.credential_version};
        state.receipts.set(receipt.request_id, receipt);
        result = ok(receipt); break;
      }
      default: throw new Error('unexpected operation');
    }
    if (state.lost.delete(operation)) result = unavailable();
    return finish(operation, result);
  }};
  const options: DeviceIdentitySessionOptions = {serviceOrigin: origin, deviceLabel: '  意客AI Windows客户端  ', journal, vault, transport, nowSeconds: () => now};
  const session: DeviceIdentitySessionInput = {userId, sessionId: randomUUID(), isCurrent: () => state.current};
  return {state, key, journal, vault, transport, options, session, make: () => createDeviceIdentitySession(options)};
}

describe('main-only durable device identity coordinator', () => {
  it('persists registration and local key/proof before first BIND, signs exact server bytes, then rechecks identity', async () => {
    const f = fixture();
    expect(await f.make().prepare(f.session)).toEqual(succeeded);
    expect(f.state.events).toEqual(['journal.load', 'devices.register', 'devices.identity', 'vault.create', 'journal.proof', 'devices.challenge', 'devices.complete', 'devices.identity']);
    expect(f.state.record!.registration.device_label).toBe('意客AI Windows客户端');
    expect(f.state.record!.proof).toMatchObject({deviceId, sessionId: f.session.sessionId, request: {operation: 'BIND', expected_credential_version: 0, public_key: f.key.publicKey}});
  });

  it('after reconstruction and new login proves the same persisted device/key with a new request', async () => {
    const f = fixture();
    expect(await f.make().prepare(f.session)).toEqual(succeeded);
    const first = structuredClone(f.state.record!);
    f.state.events.length = 0;
    const newSession = {...f.session, sessionId: randomUUID()};
    expect(await f.make().prepare(newSession)).toEqual(succeeded);
    expect(f.state.events).toEqual(['journal.load', 'devices.registration', 'devices.receipt', 'devices.identity', 'vault.read', 'journal.proof', 'devices.challenge', 'devices.complete', 'devices.identity']);
    expect(f.state.record!.registration).toEqual(first.registration);
    expect(f.state.record!.proof!.request).toMatchObject({operation: 'PROVE', public_key: null, expected_credential_version: 1});
    expect(f.state.record!.proof!.request.request_id).not.toBe(first.proof!.request.request_id);
  });

  it('recovers a lost registration response by original GET without another registration POST', async () => {
    const f = fixture(); f.state.lost.add('devices.register');
    expect(await f.make().prepare(f.session)).toEqual({state: 'REGISTRATION_UNKNOWN'});
    expect(f.state.events).toEqual(['journal.load', 'devices.register']);
    expect(await f.make().prepare(f.session)).toEqual(succeeded);
    expect(f.state.calls.filter(call => call.operation === 'devices.register')).toHaveLength(1);
    expect(f.state.calls.find(call => call.operation === 'devices.registration')!.payload.request_id).toBe(f.state.record!.registration.request_id);
  });

  it('404 remains unknown, and only explicit registration retry POSTs the same original UUID/label', async () => {
    const f = fixture();
    f.state.override = operation => operation === 'devices.register' ? unavailable() : undefined;
    expect(await f.make().prepare(f.session)).toEqual({state: 'REGISTRATION_UNKNOWN'});
    const original = structuredClone(f.state.record!.registration);
    expect(await f.make().prepare(f.session)).toEqual({state: 'REGISTRATION_UNKNOWN'});
    expect(f.state.calls.filter(call => call.operation === 'devices.register')).toHaveLength(1);
    f.state.override = () => undefined; f.options.deviceLabel = '另一个固定标签';
    expect(await f.make().prepare(f.session, {retryRegistration: true})).toEqual(succeeded);
    expect(f.state.calls.filter(call => call.operation === 'devices.register').map(call => call.payload)).toEqual([original, original]);
  });

  it('recovers a lost completion with GET + current identity, without new challenge or completion', async () => {
    const f = fixture(); f.state.lost.add('devices.complete');
    expect(await f.make().prepare(f.session)).toEqual({state: 'PROOF_UNKNOWN'});
    const originalProof = structuredClone(f.state.record!.proof);
    const before = f.state.calls.length;
    expect(await f.make().prepare(f.session)).toEqual(succeeded);
    expect(f.state.calls.slice(before).map(call => call.operation)).toEqual(['devices.registration', 'devices.receipt', 'devices.identity']);
    expect(f.state.record!.proof).toEqual(originalProof);
  });

  it.each(['PENDING', 'MISSING'] as const)('same-epoch %s proof is unknown until explicit retry reuses its original UUID', async state => {
    const f = fixture(); f.state.lost.add('devices.challenge');
    expect(await f.make().prepare(f.session)).toEqual({state: 'PROOF_UNKNOWN'});
    const request = structuredClone(f.state.record!.proof!.request);
    if (state === 'MISSING') f.state.receipts.delete(request.request_id);
    const before = f.state.calls.length;
    expect(await f.make().prepare(f.session)).toEqual({state: 'PROOF_UNKNOWN'});
    expect(f.state.calls.slice(before).some(call => ['devices.challenge', 'devices.complete'].includes(call.operation))).toBe(false);
    expect(await f.make().prepare(f.session, {retryProof: true})).toEqual(succeeded);
    expect(f.state.calls.filter(call => call.operation === 'devices.challenge').map(call => call.payload.request)).toEqual([request, request]);
  });

  it.each(['PENDING', 'MISSING', 'SUCCEEDED'] as const)('old-epoch %s receipt is never current authorization or replayed completion', async state => {
    const f = fixture(); f.state.lost.add(state === 'SUCCEEDED' ? 'devices.complete' : 'devices.challenge');
    await f.make().prepare(f.session);
    expect(f.state.record?.proof).toBeTruthy();
    const old = structuredClone(f.state.record!.proof!);
    if (state === 'MISSING') f.state.receipts.delete(old.request.request_id);
    const before = f.state.calls.length;
    expect(await f.make().prepare({...f.session, sessionId: randomUUID()}, {retryProof: true})).toEqual(succeeded);
    expect(f.state.record!.proof!.request.request_id).not.toBe(old.request.request_id);
    const calls = f.state.calls.slice(before);
    expect(calls.find(call => call.operation === 'devices.challenge')!.payload.request.request_id).not.toBe(old.request.request_id);
    expect(calls.filter(call => call.operation === 'devices.complete')).toHaveLength(1);
    expect(f.state.record!.proof!.request.operation).toBe(state === 'SUCCEEDED' ? 'PROVE' : 'BIND');
  });

  it.each(['REJECTED', 'EXPIRED'] as const)('consumed %s proof is replaced only by the next prepare, never replayed', async state => {
    const f = fixture(); f.state.lost.add('devices.challenge'); await f.make().prepare(f.session);
    expect(f.state.record?.proof).toBeTruthy();
    const old = f.state.record!.proof!.request;
    f.state.receipts.set(old.request_id, {request_id: old.request_id, device_id: deviceId, operation: 'BIND', state, credential_version: null});
    expect(await f.make().prepare(f.session, {retryProof: true})).toEqual(succeeded);
    expect(f.state.record!.proof!.request.request_id).not.toBe(old.request_id);
  });

  it('old proof read failure remains unknown and does not overwrite proof or issue any POST', async () => {
    const f = fixture(); f.state.lost.add('devices.challenge'); await f.make().prepare(f.session);
    expect(f.state.record?.proof).toBeTruthy();
    const old = structuredClone(f.state.record!.proof);
    const before = f.state.calls.length;
    f.state.override = operation => operation === 'devices.receipt' ? unavailable() : undefined;
    expect(await f.make().prepare({...f.session, sessionId: randomUUID()})).toEqual({state: 'PROOF_UNKNOWN'});
    expect(f.state.record!.proof).toEqual(old);
    expect(f.state.calls.slice(before).map(call => call.operation)).toEqual(['devices.registration', 'devices.receipt']);
  });

  it.each(['REVOKED', 'KEY_MISSING', 'KEY_MISMATCH'] as const)('stops at %s without replacing a bound device key or proving', async reason => {
    const f = fixture(); await f.make().prepare(f.session);
    expect(f.state.record?.proof).toBeTruthy();
    f.state.events.length = 0;
    if (reason === 'REVOKED') f.state.identity.device_status = 'REVOKED';
    if (reason === 'KEY_MISSING') f.state.key = null;
    if (reason === 'KEY_MISMATCH') f.state.identity.public_key = Buffer.alloc(32, 2).toString('base64url');
    expect(await f.make().prepare({...f.session, sessionId: randomUUID()})).toEqual({state: reason});
    expect(f.state.events.some(event => ['vault.create', 'journal.proof', 'devices.challenge', 'devices.complete'].includes(event))).toBe(false);
  });

  it('rechecks current identity after completion and refuses a version race without another proof loop', async () => {
    const f = fixture();
    f.state.after = async event => {if (event === 'devices.complete') f.state.identity.credential_version = 2;};
    expect(await f.make().prepare(f.session)).toEqual({state: 'FAILED', error: 'DEVICE_IDENTITY_VERSION_CHANGED'});
    expect(f.state.calls.filter(call => call.operation === 'devices.challenge')).toHaveLength(1);
  });

  it.each(['journal.load', 'vault.create', 'journal.proof'] as const)('storage failure at %s stops subsequent network writes and sanitizes diagnostics', async event => {
    const f = fixture();
    f.state.after = async value => {if (value === event) throw new Error('/private/key/secret-token');};
    expect(await f.make().prepare(f.session)).toEqual({state: 'FAILED', error: 'DEVICE_IDENTITY_FAILED'});
    expect(f.state.events.at(-1)).toBe(event);
    expect(f.state.calls.some(call => call.operation === 'devices.challenge')).toBe(false);
    if (event === 'journal.load') expect(f.state.calls).toHaveLength(0);
  });

  it('CAS rejection before durable proof prevents challenge POST', async () => {
    const f = fixture();
    f.journal.setProof = async () => {throw new Error('private CAS conflict');};
    expect(await f.make().prepare(f.session)).toEqual({state: 'FAILED', error: 'DEVICE_IDENTITY_FAILED'});
    expect(f.state.calls.map(call => call.operation)).toEqual(['devices.register', 'devices.identity']);
  });

  it.each(['devices.register', 'devices.identity', 'devices.challenge', 'devices.complete'] as const)('rejects malformed %s data with a fixed failure and no private response leakage', async operation => {
    const f = fixture(); f.state.override = value => value === operation ? ok({private: 'secret-token'}) : undefined;
    expect(await f.make().prepare(f.session)).toEqual({state: 'FAILED', error: 'DEVICE_IDENTITY_FAILED'});
    expect(f.state.calls.at(-1)?.operation).toBe(operation);
  });

  it('rejects a registration receipt bound to a different original request', async () => {
    const f = fixture();
    f.state.override = operation => operation === 'devices.register' ? ok({request_id: randomUUID(), device_id: deviceId, device_label: '意客AI Windows客户端', state: 'SUCCEEDED', registered_at: '2026-09-10T12:00:00Z'}) : undefined;
    expect(await f.make().prepare(f.session)).toEqual({state: 'FAILED', error: 'DEVICE_IDENTITY_FAILED'});
    expect(f.state.calls).toHaveLength(1);
  });

  it.each(['journal.load', 'devices.register', 'devices.identity', 'vault.create', 'journal.proof', 'devices.challenge', 'devices.complete', 'final.identity'] as const)('drops a changed session after %s before any subsequent action', async boundary => {
    const f = fixture(); let identityReads = 0;
    f.state.after = async event => {
      if (event === 'devices.identity') identityReads++;
      if (event === boundary || boundary === 'final.identity' && identityReads === 2) f.state.current = false;
    };
    expect(await f.make().prepare(f.session)).toEqual({state: 'SESSION_CHANGED'});
    expect(f.state.events.at(-1)).toBe(boundary === 'final.identity' ? 'devices.identity' : boundary);
  });

  it.each(['devices.receipt', 'devices.identity', 'vault.read'] as const)('drops a changed session after recovery %s before proof writes', async boundary => {
    const f = fixture(); expect(await f.make().prepare(f.session)).toEqual(succeeded);
    f.state.events.length = 0;
    f.state.after = async event => {if (event === boundary) f.state.current = false;};
    expect(await f.make().prepare({...f.session, sessionId: randomUUID()})).toEqual({state: 'SESSION_CHANGED'});
    expect(f.state.events.at(-1)).toBe(boundary);
    expect(f.state.events).not.toContain('journal.proof');
  });

  it('does no IO for a session already stale before prepare', async () => {
    const f = fixture(); f.state.current = false;
    expect(await f.make().prepare(f.session)).toEqual({state: 'SESSION_CHANGED'});
    expect(f.state.events).toEqual([]);
  });

  it('serializes concurrent prepares and survives a prior failure without duplicate registration/proof', async () => {
    const f = fixture(); const coordinator = f.make();
    f.state.after = async event => {if (event === 'journal.load') {f.state.after = async () => {}; throw new Error('private');}};
    expect(await coordinator.prepare(f.session)).toMatchObject({state: 'FAILED'});
    // The journal write may have succeeded; explicit recovery uses the persisted UUID.
    const results = await Promise.all(Array.from({length: 5}, () => coordinator.prepare(f.session, {retryRegistration: true})));
    expect(results).toEqual(Array.from({length: 5}, () => succeeded));
    expect(f.state.calls.filter(call => call.operation === 'devices.register')).toHaveLength(1);
    expect(f.state.calls.filter(call => call.operation === 'devices.complete')).toHaveLength(1);
  });

  it('snapshots trusted config/session/retry values before enqueue', async () => {
    const f = fixture(); const coordinator = f.make();
    const session = {...f.session}; const retry = {retryRegistration: false};
    const pending = coordinator.prepare(session, retry);
    session.userId = 'changed'; session.sessionId = randomUUID(); session.isCurrent = () => false;
    retry.retryRegistration = true; f.options.deviceLabel = 'changed'; f.options.serviceOrigin = 'https://other.example';
    expect(await pending).toEqual(succeeded);
    expect(f.state.record!.scope).toEqual({serviceOrigin: origin, userId});
    expect(f.state.record!.proof!.sessionId).toBe(f.session.sessionId);
    expect(f.state.record!.registration.device_label).toBe('意客AI Windows客户端');
  });

  it('does not acquire retry permission from an options mutation while another prepare is pending', async () => {
    const f = fixture(); const coordinator = f.make();
    let release!: () => void;
    const blocked = new Promise<void>(resolve => {release = resolve;});
    f.state.after = async event => {if (event === 'journal.load') await blocked;};
    f.state.override = operation => operation === 'devices.register' ? unavailable() : undefined;
    const first = coordinator.prepare(f.session);
    const retry = {retryRegistration: false};
    const second = coordinator.prepare(f.session, retry);
    retry.retryRegistration = true;
    await Promise.resolve();
    expect(f.state.calls).toHaveLength(0);
    release();
    expect(await first).toEqual({state: 'REGISTRATION_UNKNOWN'});
    expect(await second).toEqual({state: 'REGISTRATION_UNKNOWN'});
    expect(f.state.calls.map(call => call.operation)).toEqual(['devices.register', 'devices.registration']);
  });

  it('a queued prepare checks the current epoch before doing any IO', async () => {
    const f = fixture(); const coordinator = f.make();
    f.state.after = async event => {if (event === 'devices.register') f.state.current = false;};
    const first = coordinator.prepare(f.session);
    const second = coordinator.prepare(f.session);
    expect(await first).toEqual({state: 'SESSION_CHANGED'});
    expect(await second).toEqual({state: 'SESSION_CHANGED'});
    expect(f.state.events).toEqual(['journal.load', 'devices.register']);
  });

  it('a rejected IO result after epoch change still returns SESSION_CHANGED', async () => {
    const f = fixture();
    f.state.after = async event => {if (event === 'journal.proof') {f.state.current = false; throw new Error('private failure');}};
    expect(await f.make().prepare(f.session)).toEqual({state: 'SESSION_CHANGED'});
    expect(f.state.events.at(-1)).toBe('journal.proof');
  });

  it.each(['devices.receipt', 'devices.complete'] as const)('rejects a proof receipt for another request at %s', async operation => {
    const f = fixture();
    if (operation === 'devices.receipt') {
      f.state.lost.add('devices.challenge');
      expect(await f.make().prepare(f.session)).toEqual({state: 'PROOF_UNKNOWN'});
    }
    f.state.override = value => value === operation ? ok({request_id: randomUUID(), device_id: deviceId, operation: 'BIND', state: 'SUCCEEDED', credential_version: 1}) : undefined;
    expect(await f.make().prepare(f.session)).toEqual({state: 'FAILED', error: 'DEVICE_IDENTITY_FAILED'});
    expect(f.state.calls.at(-1)?.operation).toBe(operation);
  });

  it.each(['devices.register', 'devices.challenge', 'devices.complete'] as const)('transport exception at %s produces only the narrow unknown state and no retry', async operation => {
    const f = fixture();
    f.state.after = async value => {if (value === operation) throw new Error('/private/credentials');};
    expect(await f.make().prepare(f.session)).toEqual({state: operation === 'devices.register' ? 'REGISTRATION_UNKNOWN' : 'PROOF_UNKNOWN'});
    expect(f.state.calls.filter(call => call.operation === operation)).toHaveLength(1);
    expect(f.state.events.at(-1)).toBe(operation);
  });

  it('does not retry a registration read authentication failure even with explicit retry permission', async () => {
    const f = fixture(); f.state.lost.add('devices.register');
    expect(await f.make().prepare(f.session)).toEqual({state: 'REGISTRATION_UNKNOWN'});
    f.state.override = operation => operation === 'devices.registration' ? {ok: false, status: 401, error: 'invalid_session'} : undefined;
    expect(await f.make().prepare(f.session, {retryRegistration: true})).toEqual({state: 'REGISTRATION_UNKNOWN'});
    expect(f.state.calls.filter(call => call.operation === 'devices.register')).toHaveLength(1);
  });

  it('an expired server challenge is never signed/completed or automatically replaced', async () => {
    const f = fixture(); f.options.nowSeconds = () => now + 120;
    expect(await f.make().prepare(f.session)).toEqual({state: 'FAILED', error: 'DEVICE_IDENTITY_FAILED'});
    expect(f.state.calls.at(-1)?.operation).toBe('devices.challenge');
    expect(f.state.calls.filter(call => call.operation === 'devices.challenge')).toHaveLength(1);
  });

  it('a late revoke after completion is returned as REVOKED rather than READY', async () => {
    const f = fixture();
    f.state.after = async event => {if (event === 'devices.complete') f.state.identity.device_status = 'REVOKED';};
    expect(await f.make().prepare(f.session)).toEqual({state: 'REVOKED'});
  });

  it.each([
    {userId: 'other', sessionId: 'not-uuid', isCurrent: () => true},
    {userId: '', sessionId: randomUUID(), isCurrent: () => true},
    {userId, sessionId: randomUUID(), isCurrent: true},
  ])('invalid session inputs fail without IO', async session => {
    const f = fixture();
    expect(await f.make().prepare(session as unknown as DeviceIdentitySessionInput)).toEqual({state: 'FAILED', error: 'DEVICE_IDENTITY_FAILED'});
    expect(f.state.events).toEqual([]);
  });

  it.each(['', 'http://untrusted.example', 'https://pilot.example/path', 'https://pilot.example/'])('rejects invalid fixed service origin %s at construction', serviceOrigin => {
    const f = fixture();
    expect(() => createDeviceIdentitySession({...f.options, serviceOrigin})).toThrowError('DEVICE_IDENTITY_INVALID_CONFIG');
  });
  it.each(['', '\0', '字'.repeat(129)])('rejects invalid fixed label at construction', deviceLabel => {
    const f = fixture();
    expect(() => createDeviceIdentitySession({...f.options, deviceLabel})).toThrowError('DEVICE_IDENTITY_INVALID_CONFIG');
  });
});
