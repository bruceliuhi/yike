import type {DeviceKeyProtection} from './deviceKeyVault';
import {candidateSubmissionSchema, type CandidateSubmission} from '../shared/candidateSubmission';
import {deviceUuidSchema} from '../shared/deviceRegistration';
import {createHash} from 'node:crypto';
import {constants} from 'node:fs';
import {lstat, mkdir, open, opendir} from 'node:fs/promises';
import path from 'node:path';

export interface CandidateJournalScope {readonly serviceOrigin: string; readonly userId: string}
export interface CandidateBatchKey {platformRunId: string; requestId: string}
export interface CandidateJournal {
  persist(scope: CandidateJournalScope, batch: CandidateSubmission): Promise<{batch: CandidateSubmission; created: boolean}>;
  read(scope: CandidateJournalScope, key: CandidateBatchKey): Promise<CandidateSubmission | null>;
  list(scope: CandidateJournalScope): Promise<CandidateBatchKey[]>;
}
const MAX_ENVELOPE_BYTES = 4 * 1024 * 1024;
const MAX_PLAIN_BYTES = MAX_ENVELOPE_BYTES + 16_384;
const MAX_CIPHER_BYTES = 8 * 1024 * 1024;
const MAX_LIST_RECORDS = 1000;
// Shared between factories; the desktop application owns the process single-instance lock.
const pendingFiles = new Map<string, Promise<void>>();
type ErrorCode = 'INVALID_SCOPE' | 'INVALID_RECORD' | 'PROTECTION_UNAVAILABLE' | 'PROTECTION_FAILED' | 'STORAGE_FAILED' | 'CONFLICT' | 'LIMIT_EXCEEDED';
class JournalError extends Error {constructor(code: ErrorCode) {super(`CANDIDATE_JOURNAL_${code}`);}}
function fail(code: ErrorCode): never {throw new JournalError(code);}
function hasCode(error: unknown, code: string): boolean {return error instanceof Error && 'code' in error && error.code === code;}
function exact(value: unknown, fields: string[]): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) &&
    Reflect.ownKeys(value).length === fields.length && fields.every(field => Object.hasOwn(value, field));
}
function parseScope(value: unknown): CandidateJournalScope {
  try {
    if (!exact(value, ['serviceOrigin', 'userId'])) throw new Error();
    const {serviceOrigin, userId} = value;
    if (typeof serviceOrigin !== 'string' || serviceOrigin.length > 2048 || typeof userId !== 'string' ||
        Array.from(userId).length < 1 || Array.from(userId).length > 256 || userId !== userId.trim() ||
        /^[\u0085]|[\u0085]$/.test(userId) || /[\x00-\x1f]/.test(userId) ||
        Array.from(userId).some(character => /^[\ud800-\udfff]$/.test(character))) throw new Error();
    const url = new URL(serviceOrigin);
    const loopback = url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
    if (url.origin !== serviceOrigin || (url.protocol !== 'https:' && !loopback) || url.username || url.password) throw new Error();
    return Object.freeze({serviceOrigin, userId});
  } catch {return fail('INVALID_SCOPE');}
}
function parseKey(value: unknown): CandidateBatchKey {
  try {
    if (!exact(value, ['platformRunId', 'requestId']) || typeof value.requestId !== 'string' ||
        !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(value.requestId)) throw new Error();
    return Object.freeze({platformRunId: deviceUuidSchema.parse(value.platformRunId), requestId: value.requestId});
  } catch {return fail('INVALID_RECORD');}
}
function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === 'object') {
    Object.values(value).forEach(deepFreeze); Object.freeze(value);
  }
  return value;
}
function parseBatch(value: unknown): CandidateSubmission {
  let batch: CandidateSubmission;
  try {
    // Zod constructs a detached, normalized object including explicit nullable defaults.
    batch = candidateSubmissionSchema.parse(value);
    parseKey({platformRunId: batch.execution.platform_run_id, requestId: batch.request_id});
  } catch {return fail('INVALID_RECORD');}
  if (Buffer.byteLength(JSON.stringify({batch, signature: 'A'.repeat(86)})) > MAX_ENVELOPE_BYTES) fail('LIMIT_EXCEEDED');
  return deepFreeze(batch);
}
function batchKey(batch: CandidateSubmission): CandidateBatchKey {
  return parseKey({platformRunId: batch.execution.platform_run_id, requestId: batch.request_id});
}
function hash(value: unknown): string {return createHash('sha256').update(JSON.stringify(value)).digest('hex');}
function prefix(scope: CandidateJournalScope): string {return `${hash(scope)}-`;}
function recordName(scope: CandidateJournalScope, key: CandidateBatchKey): string {return `${prefix(scope)}${hash(key)}.candidate`;}
function requireProtection(protection: DeviceKeyProtection) {
  let available = false;
  try {available = protection.isEncryptionAvailable() === true;} catch { /* Fixed code only. */ }
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
async function readExisting(filename: string, scope: CandidateJournalScope, expectedKey: CandidateBatchKey | null,
  protection: DeviceKeyProtection): Promise<CandidateSubmission | null> {
  let metadata;
  try {metadata = await lstat(filename);} catch (error) {if (hasCode(error, 'ENOENT')) return null; return fail('STORAGE_FAILED');}
  if (!metadata.isFile() || metadata.isSymbolicLink() || metadata.size < 1 || metadata.size > MAX_CIPHER_BYTES) fail('INVALID_RECORD');
  let bytes: Buffer;
  try {
    // O_RDWR permits Windows FlushFileBuffers; existing content is never rewritten.
    const handle = await open(filename, constants.O_RDWR | (constants.O_NOFOLLOW ?? 0));
    try {
      const actual = await handle.stat();
      if (!actual.isFile() || actual.dev !== metadata.dev || actual.ino !== metadata.ino) throw new Error();
      const buffer = Buffer.alloc(MAX_CIPHER_BYTES + 1); let size = 0;
      while (size < buffer.length) {
        const result = await handle.read(buffer, size, buffer.length - size, size);
        if (!result.bytesRead) break;
        size += result.bytesRead;
      }
      if (!size || size > MAX_CIPHER_BYTES) throw new Error();
      bytes = buffer.subarray(0, size);
      await handle.sync(); // Prior full writes with unknown durability require a successful sync.
    } finally {await handle.close();}
  } catch {return fail('STORAGE_FAILED');}
  let plain: string;
  try {plain = protection.decryptString(bytes);} catch {return fail('PROTECTION_FAILED');}
  try {
    if (typeof plain !== 'string' || Buffer.byteLength(plain) > MAX_PLAIN_BYTES) throw new Error();
    const raw: unknown = JSON.parse(plain);
    if (!exact(raw, ['version', 'scope', 'key', 'batch']) || raw.version !== 1) throw new Error();
    const savedScope = parseScope(raw.scope); const key = parseKey(raw.key); const batch = parseBatch(raw.batch);
    if (savedScope.serviceOrigin !== scope.serviceOrigin || savedScope.userId !== scope.userId ||
        JSON.stringify(key) !== JSON.stringify(batchKey(batch)) ||
        (expectedKey !== null && JSON.stringify(key) !== JSON.stringify(expectedKey)) ||
        path.basename(filename) !== recordName(savedScope, key) ||
        JSON.stringify({version: 1, scope: savedScope, key, batch}) !== plain) throw new Error();
    return batch;
  } catch {return fail('INVALID_RECORD');}
}
async function serialized<T>(filename: string, action: () => Promise<T>): Promise<T> {
  const key = process.platform === 'win32' ? filename.toLowerCase() : filename;
  const result = (pendingFiles.get(key) ?? Promise.resolve()).then(action);
  const settled = result.then(() => undefined, () => undefined); pendingFiles.set(key, settled);
  void settled.then(() => {if (pendingFiles.get(key) === settled) pendingFiles.delete(key);});
  return result;
}

/** Trusted fixed main-process storage. Entries are never updated, replaced, or deleted. */
export function createCandidateJournal(options: {directory: string; protection: DeviceKeyProtection}): CandidateJournal {
  if (typeof options.directory !== 'string' || !path.isAbsolute(options.directory) ||
      path.resolve(options.directory) === path.parse(options.directory).root) fail('STORAGE_FAILED');
  const directory = path.resolve(options.directory); const protection = options.protection;
  return {
    async persist(inputScope, inputBatch) {
      // Snapshot and enforce signed-upload bytes before queueing or touching storage.
      const scope = parseScope(inputScope); const batch = parseBatch(inputBatch); const key = batchKey(batch);
      const target = path.join(directory, recordName(scope, key));
      function existingResult(existing: CandidateSubmission) {
        if (JSON.stringify(existing) !== JSON.stringify(batch)) fail('CONFLICT');
        return {batch: existing, created: false};
      }
      return serialized(target, async () => {
        requireProtection(protection); await directoryReady(directory, true);
        const existing = await readExisting(target, scope, key, protection);
        if (existing) return existingResult(existing);
        let bytes: Buffer;
        try {
          const plain = JSON.stringify({version: 1, scope, key, batch});
          if (Buffer.byteLength(plain) > MAX_PLAIN_BYTES) throw new Error();
          const encrypted = protection.encryptString(plain);
          if (!Buffer.isBuffer(encrypted) || !encrypted.length || encrypted.length > MAX_CIPHER_BYTES) throw new Error();
          bytes = Buffer.from(encrypted);
        } catch {return fail('PROTECTION_FAILED');}
        let handle;
        try {handle = await open(target, 'wx', 0o600);} catch (error) {
          if (hasCode(error, 'EEXIST')) {
            const concurrent = await readExisting(target, scope, key, protection);
            if (concurrent) return existingResult(concurrent);
          }
          return fail('STORAGE_FAILED');
        }
        try {
          try {await handle.writeFile(bytes); await handle.sync();} finally {await handle.close();}
        } catch {return fail('STORAGE_FAILED');} // Keep partial/unknown bytes for explicit recovery.
        return {batch, created: true};
      });
    },
    async read(inputScope, inputKey) {
      const scope = parseScope(inputScope); const key = parseKey(inputKey); const target = path.join(directory, recordName(scope, key));
      return serialized(target, async () => {
        requireProtection(protection); if (!await directoryReady(directory, false)) return null;
        return readExisting(target, scope, key, protection);
      });
    },
    async list(inputScope) {
      const scope = parseScope(inputScope); const start = prefix(scope);
      requireProtection(protection); if (!await directoryReady(directory, false)) return [];
      const names: string[] = [];
      try {
        // Enumerate bounded names first, so overflow rejects the whole list before decoding bodies.
        for await (const entry of await opendir(directory)) {
          if (!entry.name.startsWith(start) || !entry.name.endsWith('.candidate')) continue;
          if (!/^[0-9a-f]{64}$/.test(entry.name.slice(start.length, -'.candidate'.length))) fail('INVALID_RECORD');
          names.push(entry.name); if (names.length > MAX_LIST_RECORDS) fail('LIMIT_EXCEEDED');
        }
      } catch (error) {if (error instanceof JournalError) throw error; return fail('STORAGE_FAILED');}
      const keys: CandidateBatchKey[] = [];
      for (const name of names.sort()) {
        const target = path.join(directory, name);
        const batch = await serialized(target, () => readExisting(target, scope, null, protection));
        if (!batch) fail('STORAGE_FAILED');
        keys.push(batchKey(batch)); // Do not accumulate record bodies across files.
      }
      return keys;
    },
  };
}
