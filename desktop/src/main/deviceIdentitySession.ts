import {randomUUID} from 'node:crypto';
import {z} from 'zod';
import type {ApiResult} from '../shared/contracts';
import {deviceRegistrationRequestSchema, deviceUuidSchema, parseDeviceIdentity, parseDeviceRegistrationReceipt} from '../shared/deviceRegistration';
import {deviceChallengeRequestSchema, parseDeviceProofReceipt, type DeviceProofReceipt} from '../shared/deviceProof';
import type {DeviceIdentityJournal} from './deviceIdentityJournal';
import type {DeviceKeyMaterial, DeviceKeyScope} from './deviceKeyVault';
import {signDeviceChallenge} from './deviceProofSigner';
import {configuredService} from './serviceClient';

export type DeviceIdentityResult =
  | {state: 'READY'; deviceId: string; credentialVersion: number}
  | {state: 'REGISTRATION_UNKNOWN' | 'PROOF_UNKNOWN' | 'REVOKED' | 'KEY_MISSING' | 'KEY_MISMATCH' | 'SESSION_CHANGED' | 'FAILED'; error?: 'DEVICE_IDENTITY_FAILED' | 'DEVICE_IDENTITY_VERSION_CHANGED'};
export interface DeviceIdentitySessionInput {
  readonly userId: string;
  readonly sessionId: string;
  readonly isCurrent: () => boolean;
}
export interface DeviceIdentitySessionOptions {
  serviceOrigin: string;
  deviceLabel: string;
  transport: {requestDevice(input: unknown): Promise<ApiResult>};
  journal: DeviceIdentityJournal;
  vault: {
    read(scope: DeviceKeyScope): Promise<DeviceKeyMaterial | null>;
    getOrCreate(scope: DeviceKeyScope): Promise<DeviceKeyMaterial>;
  };
  nowSeconds?: () => number;
}
export interface DeviceIdentityRetryOptions {retryRegistration?: boolean; retryProof?: boolean}

const sessionSchema = z.object({
  userId: z.string().min(1).refine(value => Array.from(value).length <= 256 && value === value.trim() && !/[\x00-\x1f]/.test(value)),
  sessionId: deviceUuidSchema,
  isCurrent: z.custom<() => boolean>(value => typeof value === 'function'),
}).strict();
const retrySchema = z.object({retryRegistration: z.boolean().optional(), retryProof: z.boolean().optional()}).strict();
const changed = Symbol('session changed');
const failed = (): DeviceIdentityResult => ({state: 'FAILED', error: 'DEVICE_IDENTITY_FAILED'});

export function createDeviceIdentitySession(options: DeviceIdentitySessionOptions) {
  const {serviceOrigin, transport, journal, vault} = options;
  const nowSeconds = options.nowSeconds ?? (() => Math.floor(Date.now() / 1000));
  let deviceLabel: string;
  try {
    if (serviceOrigin !== configuredService(serviceOrigin, {packaged: false, allowLoopbackHttp: true})) throw new Error();
    deviceLabel = deviceRegistrationRequestSchema.parse({request_id: '00000000-0000-0000-0000-000000000000', device_label: options.deviceLabel}).device_label;
  } catch { throw new Error('DEVICE_IDENTITY_INVALID_CONFIG'); }
  let queue: Promise<unknown> = Promise.resolve();

  async function run(session: DeviceIdentitySessionInput, retry: DeviceIdentityRetryOptions): Promise<DeviceIdentityResult> {
    function guard() { if (session.isCurrent() !== true) throw changed; }
    async function checked<T>(action: () => Promise<T>): Promise<T> {
      guard();
      try { const result = await action(); guard(); return result; }
      catch (error) { guard(); throw error; }
    }
    async function http(operation: string, payload: unknown): Promise<ApiResult> {
      try { return await checked(() => transport.requestDevice({operation, payload})); }
      catch (error) {
        if (error === changed) throw error;
        return {ok: false, status: 0, error: 'SERVICE_UNAVAILABLE'};
      }
    }
    try {
      guard();
      const scope = {serviceOrigin, userId: session.userId};
      const {record, created} = await checked(() => journal.loadOrCreate(scope, deviceLabel));
      let registration = await http(created ? 'devices.register' : 'devices.registration',
        created ? record.registration : {request_id: record.registration.request_id});
      if (!registration.ok && !created && registration.status === 404 && registration.error === 'request_not_found' && retry.retryRegistration) {
        registration = await http('devices.register', record.registration);
      }
      if (!registration.ok) return {state: 'REGISTRATION_UNKNOWN'};
      const receipt = parseDeviceRegistrationReceipt(registration.data, record.registration);
      const deviceId = receipt.device_id;
      const previous = record.proof;
      let previousReceipt: DeviceProofReceipt | null = null;
      if (previous) {
        if (previous.deviceId !== deviceId) throw new Error();
        const response = await http('devices.receipt', {request_id: previous.request.request_id});
        if (response.ok) previousReceipt = parseDeviceProofReceipt(response.data, {deviceId, request: previous.request});
        else if (response.status !== 404 || response.error !== 'request_not_found') return {state: 'PROOF_UNKNOWN'};
      }

      const identityResponse = await http('devices.identity', {device_id: deviceId});
      if (!identityResponse.ok) return failed();
      const identity = parseDeviceIdentity(identityResponse.data, deviceId);
      if (identity.device_status === 'REVOKED') return {state: 'REVOKED'};
      const keyScope = {...scope, deviceId};
      const key = await checked(() => identity.credential_version === 0 ? vault.getOrCreate(keyScope) : vault.read(keyScope));
      if (!key) return {state: 'KEY_MISSING'};
      if (key.scope.serviceOrigin !== serviceOrigin || key.scope.userId !== session.userId || key.scope.deviceId !== deviceId ||
          identity.public_key !== null && identity.public_key !== key.publicKey) return {state: 'KEY_MISMATCH'};

      const sameSession = previous?.sessionId === session.sessionId;
      function ready(version: number, currentIdentity: ReturnType<typeof parseDeviceIdentity>): DeviceIdentityResult {
        guard();
        if (currentIdentity.device_status === 'REVOKED') return {state: 'REVOKED'};
        if (currentIdentity.public_key !== key!.publicKey) return {state: 'KEY_MISMATCH'};
        if (currentIdentity.credential_version !== version) return {state: 'FAILED', error: 'DEVICE_IDENTITY_VERSION_CHANGED'};
        return {state: 'READY', deviceId, credentialVersion: version};
      }
      if (sameSession && previousReceipt?.state === 'SUCCEEDED') {
        return ready(previousReceipt.credential_version!, identity);
      }
      const retryPrevious = sameSession && (!previousReceipt || previousReceipt.state === 'PENDING');
      if (retryPrevious && !retry.retryProof) return {state: 'PROOF_UNKNOWN'};
      let proof = previous;
      if (!retryPrevious) {
        const request = deviceChallengeRequestSchema.parse({
          request_id: randomUUID(), operation: identity.credential_version === 0 ? 'BIND' : 'PROVE',
          expected_credential_version: identity.credential_version,
          public_key: identity.credential_version === 0 ? key.publicKey : null,
        });
        proof = {deviceId, sessionId: session.sessionId, request};
        await checked(() => journal.setProof(scope, record.registration.request_id, previous?.request.request_id ?? null, proof!));
      }
      if (!proof || proof.sessionId !== session.sessionId) throw new Error();
      if (proof.request.operation === 'BIND' && proof.request.public_key !== key.publicKey) return {state: 'KEY_MISMATCH'};
      const challenge = await http('devices.challenge', {device_id: deviceId, request: proof.request});
      if (!challenge.ok) return {state: 'PROOF_UNKNOWN'};
      guard();
      const completion = signDeviceChallenge({key, challenge: challenge.data,
        expected: {...keyScope, publicKey: key.publicKey, request: proof.request}, nowSeconds: nowSeconds()});
      // The signer validated the exact challenge envelope, including its canonical UUID.
      const challengeId = deviceUuidSchema.parse((challenge.data as {challenge_id: unknown}).challenge_id);
      const completed = await http('devices.complete', {device_id: deviceId, challenge_id: challengeId, proof: completion});
      if (!completed.ok) return {state: 'PROOF_UNKNOWN'};
      const result = parseDeviceProofReceipt(completed.data, {deviceId, request: proof.request});
      if (result.state !== 'SUCCEEDED') return {state: 'PROOF_UNKNOWN'};
      const latest = await http('devices.identity', {device_id: deviceId});
      if (!latest.ok) return failed();
      return ready(result.credential_version!, parseDeviceIdentity(latest.data, deviceId));
    } catch (error) {
      return error === changed ? {state: 'SESSION_CHANGED'} : failed();
    }
  }
  return {
    prepare(input: DeviceIdentitySessionInput, inputRetry: DeviceIdentityRetryOptions = {}): Promise<DeviceIdentityResult> {
      try {
        // Parse/copy before entering the queue: mutation cannot change the chosen epoch or retry intent.
        const session = sessionSchema.parse(input);
        const retry = retrySchema.parse(inputRetry);
        const result = queue.then(() => run(session, retry));
        queue = result.then(() => undefined, () => undefined);
        return result;
      } catch { return Promise.resolve(failed()); }
    },
  };
}
