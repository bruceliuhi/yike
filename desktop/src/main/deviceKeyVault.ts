export interface DeviceKeyScope {
  readonly serviceOrigin: string;
  readonly userId: string;
  readonly deviceId: string;
}

/** Main-process only. Never return this material through IPC or logging. */
export interface DeviceKeyMaterial {
  readonly scope: DeviceKeyScope;
  readonly publicKey: string;
  readonly privateKey: string;
}

export interface DeviceKeyProtection {
  isEncryptionAvailable(): boolean;
  encryptString(value: string): Buffer;
  decryptString(value: Buffer): string;
}

const MAX_RECORD_BYTES = 65_536;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
// Shared between factories as well as callers. The app already has a single-instance lock.
const pendingFiles = new Map<string, Promise<void>>();

function exactFields(value: unknown, fields: string[]): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) &&
    Reflect.ownKeys(value).length === fields.length && fields.every(field => Object.hasOwn(value, field));
}

function parseScope(input: unknown): DeviceKeyScope {
  try {
    if (!exactFields(input, ['serviceOrigin', 'userId', 'deviceId'])) throw new Error();
    const {serviceOrigin, userId, deviceId} = input;
    if (typeof serviceOrigin !== 'string' || serviceOrigin.length > 2048 ||
        typeof userId !== 'string' || Array.from(userId).length < 1 || Array.from(userId).length > 256 ||
        userId !== userId.trim() || /[\x00-\x1f]/.test(userId) ||
        typeof deviceId !== 'string' || !UUID.test(deviceId)) throw new Error();
    const url = new URL(serviceOrigin);
    const localHttp = url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
    if (url.origin !== serviceOrigin || (url.protocol !== 'https:' && !localHttp) ||
        url.username || url.password || url.search || url.hash) throw new Error();
    return Object.freeze({serviceOrigin, userId, deviceId});
  } catch {
    throw new Error('DEVICE_KEY_INVALID_SCOPE');
  }
}

function sameScope(left: DeviceKeyScope, right: DeviceKeyScope): boolean {
  return left.serviceOrigin === right.serviceOrigin && left.userId === right.userId && left.deviceId === right.deviceId;
}

function parseRecord(plain: string, scope: DeviceKeyScope): DeviceKeyMaterial {
  try {
    if (typeof plain !== 'string' || Buffer.byteLength(plain) > MAX_RECORD_BYTES) throw new Error();
    const record: unknown = JSON.parse(plain);
    if (!exactFields(record, ['version', 'scope', 'publicKey', 'privateKey']) || record.version !== 1 ||
        typeof record.publicKey !== 'string' || !/^[A-Za-z0-9_-]{43}$/.test(record.publicKey) ||
        typeof record.privateKey !== 'string' || record.privateKey.length > 4096 ||
        !sameScope(parseScope(record.scope), scope)) throw new Error();
    const privateKey = createPrivateKey(record.privateKey);
    if (privateKey.asymmetricKeyType !== 'ed25519' ||
        privateKey.export({format: 'pem', type: 'pkcs8'}) !== record.privateKey ||
        createPublicKey(privateKey).export({format: 'jwk'}).x !== record.publicKey) throw new Error();
    return Object.freeze({scope, publicKey: record.publicKey, privateKey: record.privateKey});
  } catch {
    throw new Error('DEVICE_KEY_INVALID_RECORD');
  }
}

function hasCode(error: unknown, code: string): boolean {
  return error instanceof Error && 'code' in error && error.code === code;
}

async function readExisting(filename: string, scope: DeviceKeyScope, protection: DeviceKeyProtection): Promise<DeviceKeyMaterial | null> {
  let metadata;
  try { metadata = await lstat(filename); }
  catch (error) {
    if (hasCode(error, 'ENOENT')) return null;
    throw new Error('DEVICE_KEY_STORAGE_FAILED');
  }
  if (!metadata.isFile() || metadata.isSymbolicLink() || metadata.size < 1 || metadata.size > MAX_RECORD_BYTES) {
    throw new Error('DEVICE_KEY_INVALID_RECORD');
  }
  let bytes: Buffer;
  try {
    // Windows FlushFileBuffers requires a writable handle. No content is rewritten.
    const handle = await open(filename, constants.O_RDWR | (constants.O_NOFOLLOW ?? 0));
    try {
      if (!(await handle.stat()).isFile()) throw new Error();
      const buffer = Buffer.alloc(MAX_RECORD_BYTES + 1);
      let size = 0;
      while (size < buffer.length) {
        const result = await handle.read(buffer, size, buffer.length - size, size);
        if (!result.bytesRead) break;
        size += result.bytesRead;
      }
      if (size < 1 || size > MAX_RECORD_BYTES) throw new Error();
      bytes = buffer.subarray(0, size);
      // A previous attempt may have written all bytes but failed to flush them.
      // Reading valid ciphertext alone is not a durable-success receipt.
      await handle.sync();
    } finally { await handle.close(); }
  } catch { throw new Error('DEVICE_KEY_STORAGE_FAILED'); }
  let plain: string;
  try { plain = protection.decryptString(bytes); }
  catch { throw new Error('DEVICE_KEY_PROTECTION_FAILED'); }
  return parseRecord(plain, scope);
}

async function serialized<T>(filename: string, operation: () => Promise<T>): Promise<T> {
  const lockKey = process.platform === 'win32' ? filename.toLowerCase() : filename;
  const result = (pendingFiles.get(lockKey) ?? Promise.resolve()).then(operation);
  const settled = result.then(() => undefined, () => undefined);
  pendingFiles.set(lockKey, settled);
  void settled.then(() => { if (pendingFiles.get(lockKey) === settled) pendingFiles.delete(lockKey); });
  return result;
}

/** Directory is fixed by the trusted main-process caller, never supplied through IPC. */
export function createDeviceKeyVault(options: {directory: string; protection: DeviceKeyProtection}) {
  if (!path.isAbsolute(options.directory) || path.resolve(options.directory) === path.parse(options.directory).root) {
    throw new Error('DEVICE_KEY_STORAGE_FAILED');
  }
  const directory = path.resolve(options.directory);
  const protection = options.protection;
  return {
    async getOrCreate(input: DeviceKeyScope): Promise<DeviceKeyMaterial> {
      const scope = parseScope(input); // Snapshot before awaiting: callers cannot switch identity mid-write.
      const digest = createHash('sha256').update(JSON.stringify(scope)).digest('hex');
      const filename = path.join(directory, `${digest}.key`);
      return serialized(filename, async () => {
        let available = false;
        try { available = protection.isEncryptionAvailable() === true; }
        catch { /* Fixed error only; OS messages can contain sensitive paths. */ }
        if (!available) throw new Error('DEVICE_KEY_PROTECTION_UNAVAILABLE');
        try {
          await mkdir(directory, {recursive: true, mode: 0o700});
          if (!(await lstat(directory)).isDirectory()) throw new Error();
        } catch { throw new Error('DEVICE_KEY_STORAGE_FAILED'); }
        const existing = await readExisting(filename, scope, protection);
        if (existing) return existing;
        let key: DeviceKeyMaterial;
        let encrypted: Buffer;
        try {
          const pair = generateKeyPairSync('ed25519');
          const privateKey = pair.privateKey.export({format: 'pem', type: 'pkcs8'}).toString();
          const publicKey = pair.publicKey.export({format: 'jwk'}).x!;
          key = Object.freeze({scope, publicKey, privateKey});
          encrypted = protection.encryptString(JSON.stringify({version: 1, ...key}));
          if (!Buffer.isBuffer(encrypted) || !encrypted.length || encrypted.length > MAX_RECORD_BYTES) throw new Error();
        } catch { throw new Error('DEVICE_KEY_PROTECTION_FAILED'); }
        let handle;
        try { handle = await open(filename, 'wx', 0o600); }
        catch (error) {
          if (hasCode(error, 'EEXIST')) {
            const concurrent = await readExisting(filename, scope, protection);
            if (concurrent) return concurrent;
          }
          throw new Error('DEVICE_KEY_STORAGE_FAILED');
        }
        try {
          try { await handle.writeFile(encrypted); await handle.sync(); }
          finally { await handle.close(); }
        } catch {
          // Keep incomplete/unknown files for explicit recovery. Never replace or bind a new key.
          throw new Error('DEVICE_KEY_STORAGE_FAILED');
        }
        return key; // No BIND may be issued until this durable operation resolves.
      });
    }
  };
}
import {createHash, createPrivateKey, createPublicKey, generateKeyPairSync} from 'node:crypto';
import {constants} from 'node:fs';
import {lstat, mkdir, open} from 'node:fs/promises';
import path from 'node:path';
