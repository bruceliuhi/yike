import type { DeviceKeyProtection } from './deviceKeyVault';
import type { DeviceChallengeRequest } from '../shared/deviceProof';
import type { DeviceRegistrationRequest } from '../shared/deviceRegistration';
import { deviceRegistrationRequestSchema, deviceUuidSchema } from '../shared/deviceRegistration';
import { deviceChallengeRequestSchema } from '../shared/deviceProof';
import { createHash, randomUUID } from 'node:crypto';
import { constants } from 'node:fs';
import { lstat, mkdir, open, rename } from 'node:fs/promises';
import path from 'node:path';

export interface DeviceIdentityScope {
  readonly serviceOrigin: string;
  readonly userId: string;
}
export interface DeviceIdentityProof {
  readonly deviceId: string;
  readonly sessionId: string;
  readonly request: DeviceChallengeRequest;
}
export interface DeviceIdentityRecord {
  readonly version: 1;
  readonly scope: DeviceIdentityScope;
  readonly registration: DeviceRegistrationRequest;
  readonly proof: DeviceIdentityProof | null;
}
export interface DeviceIdentityJournal {
  read(scope: DeviceIdentityScope): Promise<DeviceIdentityRecord | null>;
  loadOrCreate(scope: DeviceIdentityScope, label: string): Promise<{record: DeviceIdentityRecord; created: boolean}>;
  setProof(scope: DeviceIdentityScope, registrationId: string, expectedProofId: string | null,
    proof: DeviceIdentityProof): Promise<DeviceIdentityRecord>;
}
const MAX_BYTES = 65_536;
// The trusted main process also owns the application's single-instance lock.
const pendingFiles = new Map<string, Promise<void>>();
type ErrorCode = 'INVALID_SCOPE' | 'INVALID_RECORD' | 'PROTECTION_UNAVAILABLE' |
  'PROTECTION_FAILED' | 'STORAGE_FAILED' | 'CONFLICT';
function fail(code: ErrorCode): never { throw new Error(`DEVICE_IDENTITY_JOURNAL_${code}`); }
function hasCode(error: unknown, code: string): boolean {
  return error instanceof Error && 'code' in error && error.code === code;
}
function exact(value: unknown, fields: string[]): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) &&
    Reflect.ownKeys(value).length === fields.length && fields.every(field => Object.hasOwn(value, field));
}
function parseScope(raw: unknown): DeviceIdentityScope {
  try {
    if (!exact(raw, ['serviceOrigin', 'userId'])) throw new Error();
    const {serviceOrigin, userId} = raw;
    if (typeof serviceOrigin !== 'string' || serviceOrigin.length > 2048 || typeof userId !== 'string' ||
        Array.from(userId).length < 1 || Array.from(userId).length > 256 || userId !== userId.trim() ||
        /^[\u0085]|[\u0085]$/.test(userId) || /[\x00-\x1f]/.test(userId) ||
        Array.from(userId).some(character => /^[\ud800-\udfff]$/.test(character))) throw new Error();
    const url = new URL(serviceOrigin);
    const loopback = url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
    if (url.origin !== serviceOrigin || (url.protocol !== 'https:' && !loopback) || url.username || url.password) throw new Error();
    return Object.freeze({serviceOrigin, userId});
  } catch { return fail('INVALID_SCOPE'); }
}
function parseProof(raw: unknown): DeviceIdentityProof {
  try {
    if (!exact(raw, ['deviceId', 'sessionId', 'request']) ||
        !exact(raw.request, ['request_id', 'operation', 'expected_credential_version', 'public_key'])) throw new Error();
    return Object.freeze({deviceId: deviceUuidSchema.parse(raw.deviceId), sessionId: deviceUuidSchema.parse(raw.sessionId),
      request: Object.freeze(deviceChallengeRequestSchema.parse(raw.request))});
  } catch { return fail('INVALID_RECORD'); }
}
function parseRecord(raw: unknown, scope: DeviceIdentityScope): DeviceIdentityRecord {
  try {
    if (!exact(raw, ['version', 'scope', 'registration', 'proof']) || raw.version !== 1 ||
        !exact(raw.registration, ['request_id', 'device_label'])) throw new Error();
    const savedScope = parseScope(raw.scope);
    if (savedScope.serviceOrigin !== scope.serviceOrigin || savedScope.userId !== scope.userId) throw new Error();
    const registration = deviceRegistrationRequestSchema.parse(raw.registration);
    if (registration.device_label !== raw.registration.device_label) throw new Error();
    return Object.freeze({version: 1, scope: savedScope, registration: Object.freeze(registration),
      proof: raw.proof === null ? null : parseProof(raw.proof)});
  } catch { return fail('INVALID_RECORD'); }
}
function requireProtection(protection: DeviceKeyProtection): void {
  let available = false;
  try { available = protection.isEncryptionAvailable() === true; } catch { /* Fixed errors only. */ }
  if (!available) fail('PROTECTION_UNAVAILABLE');
}
async function directoryReady(directory: string, create: boolean): Promise<boolean> {
  try {
    if (create) await mkdir(directory, {recursive: true, mode: 0o700});
    const info = await lstat(directory);
    if (!info.isDirectory() || info.isSymbolicLink()) throw new Error();
    return true;
  } catch (error) {
    if (!create && hasCode(error, 'ENOENT')) return false;
    return fail('STORAGE_FAILED');
  }
}
async function readExisting(filename: string, scope: DeviceIdentityScope, protection: DeviceKeyProtection): Promise<DeviceIdentityRecord | null> {
  let metadata;
  try { metadata = await lstat(filename); }
  catch (error) { if (hasCode(error, 'ENOENT')) return null; return fail('STORAGE_FAILED'); }
  if (!metadata.isFile() || metadata.isSymbolicLink() || metadata.size < 1 || metadata.size > MAX_BYTES) fail('INVALID_RECORD');
  let bytes: Buffer;
  try {
    // Windows FlushFileBuffers requires O_RDWR; no existing content is rewritten.
    const handle = await open(filename, constants.O_RDWR | (constants.O_NOFOLLOW ?? 0));
    try {
      const actual = await handle.stat();
      if (!actual.isFile() || actual.dev !== metadata.dev || actual.ino !== metadata.ino) throw new Error();
      const buffer = Buffer.alloc(MAX_BYTES + 1);
      let size = 0;
      while (size < buffer.length) {
        const result = await handle.read(buffer, size, buffer.length - size, size);
        if (!result.bytesRead) break;
        size += result.bytesRead;
      }
      if (!size || size > MAX_BYTES) throw new Error();
      bytes = buffer.subarray(0, size);
      // Complete bytes left by a failed sync are not durable success until this succeeds.
      await handle.sync();
    } finally { await handle.close(); }
  } catch { return fail('STORAGE_FAILED'); }
  let plain: string;
  try { plain = protection.decryptString(bytes); }
  catch { return fail('PROTECTION_FAILED'); }
  try {
    if (typeof plain !== 'string' || Buffer.byteLength(plain) > MAX_BYTES) throw new Error();
    return parseRecord(JSON.parse(plain), scope);
  } catch { return fail('INVALID_RECORD'); }
}
function encrypt(record: DeviceIdentityRecord, protection: DeviceKeyProtection): Buffer {
  try {
    const encrypted = protection.encryptString(JSON.stringify(record));
    if (!Buffer.isBuffer(encrypted) || !encrypted.length || encrypted.length > MAX_BYTES) throw new Error();
    return Buffer.from(encrypted);
  } catch { return fail('PROTECTION_FAILED'); }
}
async function writeExclusive(filename: string, bytes: Buffer): Promise<void> {
  // The caller distinguishes EEXIST for initial creation; partial files are never removed.
  const handle = await open(filename, 'wx', 0o600);
  try { await handle.writeFile(bytes); await handle.sync(); }
  finally { await handle.close(); }
}
async function serialized<T>(filename: string, operation: () => Promise<T>): Promise<T> {
  const key = process.platform === 'win32' ? filename.toLowerCase() : filename;
  const result = (pendingFiles.get(key) ?? Promise.resolve()).then(operation);
  const settled = result.then(() => undefined, () => undefined);
  pendingFiles.set(key, settled);
  void settled.then(() => { if (pendingFiles.get(key) === settled) pendingFiles.delete(key); });
  return result;
}

/** Main-process only: directory is trusted and fixed, never supplied by renderer/IPC. */
export function createDeviceIdentityJournal(options: {
  directory: string; protection: DeviceKeyProtection;
}): DeviceIdentityJournal {
  if (typeof options.directory !== 'string' || !path.isAbsolute(options.directory) ||
      path.resolve(options.directory) === path.parse(options.directory).root) fail('STORAGE_FAILED');
  const directory = path.resolve(options.directory);
  const protection = options.protection;
  function filename(scope: DeviceIdentityScope): string {
    return path.join(directory, `${createHash('sha256').update(JSON.stringify(scope)).digest('hex')}.identity`);
  }
  return {
    async read(input) {
      const scope = parseScope(input);
      const target = filename(scope);
      return serialized(target, async () => {
        requireProtection(protection);
        if (!await directoryReady(directory, false)) return null;
        return readExisting(target, scope, protection);
      });
    },
    async loadOrCreate(input, label) {
      const scope = parseScope(input);
      let registration: DeviceRegistrationRequest;
      try { registration = deviceRegistrationRequestSchema.parse({request_id: randomUUID(), device_label: label}); }
      catch { return fail('INVALID_RECORD'); }
      const target = filename(scope);
      return serialized(target, async () => {
        requireProtection(protection);
        await directoryReady(directory, true);
        const existing = await readExisting(target, scope, protection);
        if (existing) return {record: existing, created: false};
        const record = parseRecord({version: 1, scope, registration, proof: null}, scope);
        const encrypted = encrypt(record, protection);
        try { await writeExclusive(target, encrypted); }
        catch (error) {
          if (hasCode(error, 'EEXIST')) {
            const concurrent = await readExisting(target, scope, protection);
            if (concurrent) return {record: concurrent, created: false};
          }
          return fail('STORAGE_FAILED');
        }
        return {record, created: true};
      });
    },
    async setProof(input, registrationId, expectedProofId, suppliedProof) {
      const scope = parseScope(input);
      let expectedRegistration: string;
      let expectedProof: string | null;
      let proof: DeviceIdentityProof;
      try {
        expectedRegistration = deviceUuidSchema.parse(registrationId);
        expectedProof = expectedProofId === null ? null : deviceUuidSchema.parse(expectedProofId);
        proof = parseProof(suppliedProof);
      } catch { return fail('INVALID_RECORD'); }
      const target = filename(scope);
      return serialized(target, async () => {
        requireProtection(protection);
        if (!await directoryReady(directory, false)) return fail('CONFLICT');
        const existing = await readExisting(target, scope, protection);
        if (!existing || existing.registration.request_id !== expectedRegistration ||
            (existing.proof?.request.request_id ?? null) !== expectedProof) return fail('CONFLICT');
        const record = parseRecord({...existing, proof}, scope);
        const encrypted = encrypt(record, protection);
        const temporary = `${target}.${randomUUID()}.tmp`;
        try {
          await writeExclusive(temporary, encrypted);
          await rename(temporary, target);
        } catch { return fail('STORAGE_FAILED'); }
        const persisted = await readExisting(target, scope, protection);
        if (!persisted) return fail('STORAGE_FAILED');
        return persisted;
      });
    },
  };
}
