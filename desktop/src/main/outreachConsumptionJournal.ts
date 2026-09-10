import {createHash} from 'node:crypto';
import {constants} from 'node:fs';
import {lstat, mkdir, open} from 'node:fs/promises';
import path from 'node:path';
import type {DeviceKeyProtection} from './deviceKeyVault';

export interface OutreachConsumption {
  readonly requestId: string;
  readonly claimId: string;
  readonly contextSha256: string;
  readonly deviceId: string;
}
export interface OutreachConsumptionScope {readonly serviceOrigin: string; readonly userId: string; readonly tenantId: string}
export interface OutreachConsumptionJournal {
  consume(scope: OutreachConsumptionScope, grant: OutreachConsumption): Promise<{created: boolean}>;
  consumed(scope: OutreachConsumptionScope, requestId: string): Promise<boolean>;
}
const MAX_BYTES = 65_536;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const pendingFiles = new Map<string, Promise<void>>();
type ErrorCode = 'INVALID_SCOPE' | 'INVALID_RECORD' | 'PROTECTION_UNAVAILABLE' | 'PROTECTION_FAILED' | 'STORAGE_FAILED' | 'CONFLICT';
function fail(code: ErrorCode): never {throw new Error(`OUTREACH_CONSUMPTION_${code}`);}
function hasCode(error: unknown, code: string) {return error instanceof Error && 'code' in error && error.code === code;}
function exact(value: unknown, fields: string[]): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) &&
    Reflect.ownKeys(value).length === fields.length && fields.every(field => Object.hasOwn(value, field));
}
function identity(value: unknown): value is string {
  return typeof value === 'string' && Array.from(value).length >= 1 && Array.from(value).length <= 256 &&
    value === value.trim() && !/^[\u0085]|[\u0085]$/.test(value) && !/[\x00-\x1f]/.test(value) &&
    !Array.from(value).some(character => /^[\ud800-\udfff]$/.test(character));
}
function parseScope(value: unknown): OutreachConsumptionScope {
  try {
    if (!exact(value, ['serviceOrigin', 'userId', 'tenantId'])) throw new Error();
    const {serviceOrigin, userId, tenantId} = value;
    if (typeof serviceOrigin !== 'string' || serviceOrigin.length > 2048 || !identity(userId) || !identity(tenantId)) throw new Error();
    const url = new URL(serviceOrigin);
    const loopback = url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
    if (url.origin !== serviceOrigin || (url.protocol !== 'https:' && !loopback) || url.username || url.password) throw new Error();
    return Object.freeze({serviceOrigin, userId, tenantId});
  } catch {return fail('INVALID_SCOPE');}
}
function parseId(value: unknown): string {
  if (typeof value !== 'string' || !UUID.test(value)) fail('INVALID_RECORD');
  return value;
}
function parseGrant(value: unknown): OutreachConsumption {
  try {
    if (!exact(value, ['requestId', 'claimId', 'contextSha256', 'deviceId'])) throw new Error();
    const requestId = parseId(value.requestId); const claimId = parseId(value.claimId); const deviceId = parseId(value.deviceId);
    const contextSha256 = value.contextSha256;
    if (typeof contextSha256 !== 'string' || !/^[0-9a-f]{64}$/.test(contextSha256)) throw new Error();
    return Object.freeze({requestId, claimId, contextSha256, deviceId});
  } catch {return fail('INVALID_RECORD');}
}
function requireProtection(protection: DeviceKeyProtection) {
  let available = false;
  try {available = protection.isEncryptionAvailable() === true;} catch { /* Never expose OS messages. */ }
  if (!available) fail('PROTECTION_UNAVAILABLE');
}
async function directoryReady(directory: string, create: boolean): Promise<boolean> {
  try {
    if (create) await mkdir(directory, {recursive: true, mode: 0o700});
    const info = await lstat(directory);
    if (!info.isDirectory() || info.isSymbolicLink()) throw new Error();
    return true;
  } catch (error) {if (!create && hasCode(error, 'ENOENT')) return false; return fail('STORAGE_FAILED');}
}
async function syncDirectory(directory: string): Promise<void> {
  // Node cannot portably open/flush directories on Windows. File fsync remains mandatory there.
  if (process.platform === 'win32') return;
  const handle = await open(directory, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0));
  try {if (!(await handle.stat()).isDirectory()) throw new Error(); await handle.sync();} finally {await handle.close();}
}
async function readExisting(filename: string, scope: OutreachConsumptionScope, requestId: string, protection: DeviceKeyProtection): Promise<OutreachConsumption | null> {
  let metadata;
  try {metadata = await lstat(filename);} catch (error) {if (hasCode(error, 'ENOENT')) return null; return fail('STORAGE_FAILED');}
  if (!metadata.isFile() || metadata.isSymbolicLink() || metadata.size < 1 || metadata.size > MAX_BYTES) fail('INVALID_RECORD');
  let bytes: Buffer;
  try {
    // O_RDWR is required by Windows FlushFileBuffers; existing contents are never rewritten.
    const handle = await open(filename, constants.O_RDWR | (constants.O_NOFOLLOW ?? 0));
    try {
      const actual = await handle.stat();
      if (!actual.isFile() || actual.dev !== metadata.dev || actual.ino !== metadata.ino) throw new Error();
      const buffer = Buffer.alloc(MAX_BYTES + 1); let size = 0;
      while (size < buffer.length) {
        const result = await handle.read(buffer, size, buffer.length - size, size);
        if (!result.bytesRead) break;
        size += result.bytesRead;
      }
      if (!size || size > MAX_BYTES) throw new Error();
      bytes = buffer.subarray(0, size); await handle.sync();
    } finally {await handle.close();}
  } catch {return fail('STORAGE_FAILED');}
  let plain: string;
  try {plain = protection.decryptString(bytes);} catch {return fail('PROTECTION_FAILED');}
  try {
    if (typeof plain !== 'string' || Buffer.byteLength(plain) > MAX_BYTES) throw new Error();
    const raw: unknown = JSON.parse(plain);
    if (!exact(raw, ['version', 'scope', 'grant']) || raw.version !== 1) throw new Error();
    const savedScope = parseScope(raw.scope); const grant = parseGrant(raw.grant);
    if (JSON.stringify(savedScope) !== JSON.stringify(scope) || grant.requestId !== requestId ||
        JSON.stringify({version: 1, scope: savedScope, grant}) !== plain) throw new Error();
    return grant;
  } catch {return fail('INVALID_RECORD');}
}
async function serialized<T>(filename: string, action: () => Promise<T>): Promise<T> {
  const key = process.platform === 'win32' ? filename.toLowerCase() : filename;
  const result = (pendingFiles.get(key) ?? Promise.resolve()).then(action);
  const settled = result.then(() => undefined, () => undefined); pendingFiles.set(key, settled);
  void settled.then(() => {if (pendingFiles.get(key) === settled) pendingFiles.delete(key);});
  return result;
}

/** Main-process engineering guard, not a message/outbox journal. Never updates or removes entries.
 * Only created:true authorizes the caller's one attempt. Not resistant to user-deleted local data,
 * and not a universal power-loss guarantee or evidence of Windows/platform acceptance.
 */
export function createOutreachConsumptionJournal(options: {directory: string; protection: DeviceKeyProtection}): OutreachConsumptionJournal {
  if (typeof options.directory !== 'string' || !path.isAbsolute(options.directory) ||
      path.resolve(options.directory) === path.parse(options.directory).root) fail('STORAGE_FAILED');
  const directory = path.resolve(options.directory); const protection = options.protection;
  const filename = (scope: OutreachConsumptionScope, requestId: string) =>
    path.join(directory, `${createHash('sha256').update(JSON.stringify({scope, requestId})).digest('hex')}.consumed`);
  return {
    async consume(inputScope, inputGrant) {
      const scope = parseScope(inputScope); const grant = parseGrant(inputGrant); const target = filename(scope, grant.requestId);
      function existingResult(existing: OutreachConsumption) {
        if (JSON.stringify(existing) !== JSON.stringify(grant)) fail('CONFLICT');
        return {created: false};
      }
      return serialized(target, async () => {
        requireProtection(protection); await directoryReady(directory, true);
        const existing = await readExisting(target, scope, grant.requestId, protection);
        if (existing) return existingResult(existing);
        let bytes: Buffer;
        try {
          const encrypted = protection.encryptString(JSON.stringify({version: 1, scope, grant}));
          if (!Buffer.isBuffer(encrypted) || !encrypted.length || encrypted.length > MAX_BYTES) throw new Error();
          bytes = Buffer.from(encrypted);
        } catch {return fail('PROTECTION_FAILED');}
        let handle;
        try {handle = await open(target, 'wx', 0o600);} catch (error) {
          if (hasCode(error, 'EEXIST')) {
            const concurrent = await readExisting(target, scope, grant.requestId, protection);
            if (concurrent) return existingResult(concurrent);
          }
          return fail('STORAGE_FAILED');
        }
        try {
          try {await handle.writeFile(bytes); await handle.sync();} finally {await handle.close();}
          await syncDirectory(directory); await syncDirectory(path.dirname(directory));
        } catch {return fail('STORAGE_FAILED');} // Leave even empty/partial records in place, never retry as new.
        return {created: true};
      });
    },
    async consumed(inputScope, inputId) {
      const scope = parseScope(inputScope); const requestId = parseId(inputId); const target = filename(scope, requestId);
      return serialized(target, async () => {
        requireProtection(protection); if (!await directoryReady(directory, false)) return false;
        return (await readExisting(target, scope, requestId, protection)) !== null;
      });
    },
  };
}
