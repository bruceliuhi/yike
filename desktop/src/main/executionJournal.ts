import type {DeviceKeyProtection} from './deviceKeyVault';
import {executionOperationSchema, type ExecutionOperation} from '../shared/executionOperation';
import {deviceUuidSchema} from '../shared/deviceRegistration';
import {createHash} from 'node:crypto';
import {constants} from 'node:fs';
import {lstat, mkdir, open, opendir} from 'node:fs/promises';
import path from 'node:path';
import {researchJournalRecordSchema,type ResearchJournalRecord} from '../shared/desktopExecution';

export interface ExecutionJournalScope {readonly serviceOrigin: string; readonly userId: string}
export interface ExecutionJournal {
  persist(scope: ExecutionJournalScope, request: ExecutionOperation): Promise<{request: ExecutionOperation; created: boolean}>;
  read(scope: ExecutionJournalScope, requestId: string): Promise<ExecutionOperation | null>;
  list(scope: ExecutionJournalScope): Promise<ExecutionOperation[]>;
  persistResearch?(scope:ExecutionJournalScope,record:ResearchJournalRecord):Promise<{record:ResearchJournalRecord;created:boolean}>;
  readResearch?(scope:ExecutionJournalScope,requestId:string):Promise<ResearchJournalRecord|null>;
  listResearch?(scope:ExecutionJournalScope):Promise<ResearchJournalRecord[]>;
}
function parseResearchRecord(value:unknown):ResearchJournalRecord{
  try{return Object.freeze(researchJournalRecordSchema.parse(value));}catch{return fail('INVALID_RECORD');}
}
const MAX_BYTES = 65_536;
const MAX_LIST_RECORDS = 1000;
const pendingFiles = new Map<string, Promise<void>>();
type ErrorCode = 'INVALID_SCOPE' | 'INVALID_RECORD' | 'PROTECTION_UNAVAILABLE' | 'PROTECTION_FAILED' | 'STORAGE_FAILED' | 'CONFLICT' | 'LIMIT_EXCEEDED';
class JournalError extends Error {constructor(code: ErrorCode) {super(`EXECUTION_JOURNAL_${code}`);}}
function fail(code: ErrorCode): never {throw new JournalError(code);}
function hasCode(error: unknown, code: string): boolean {return error instanceof Error && 'code' in error && error.code === code;}
function exact(value: unknown, fields: string[]): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) &&
    Reflect.ownKeys(value).length === fields.length && fields.every(field => Object.hasOwn(value, field));
}
function parseScope(value: unknown): ExecutionJournalScope {
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
function parseRequest(value: unknown): ExecutionOperation {
  try {
    const request = executionOperationSchema.parse(value);
    if (request.targets) {request.targets.forEach(Object.freeze); Object.freeze(request.targets);}
    return Object.freeze(request);
  } catch {return fail('INVALID_RECORD');}
}
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
async function readExisting(filename: string, scope: ExecutionJournalScope, requestId: string, protection: DeviceKeyProtection): Promise<ExecutionOperation | null> {
  let metadata;
  try {metadata = await lstat(filename);} catch (error) {if (hasCode(error, 'ENOENT')) return null; return fail('STORAGE_FAILED');}
  if (!metadata.isFile() || metadata.isSymbolicLink() || metadata.size < 1 || metadata.size > MAX_BYTES) fail('INVALID_RECORD');
  let bytes: Buffer;
  try {
    // O_RDWR is required for Windows FlushFileBuffers; existing content is never rewritten.
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
      bytes = buffer.subarray(0, size);
      await handle.sync(); // Full bytes from a failed write are not durable until a sync succeeds.
    } finally {await handle.close();}
  } catch {return fail('STORAGE_FAILED');}
  let plain: string;
  try {plain = protection.decryptString(bytes);} catch {return fail('PROTECTION_FAILED');}
  try {
    if (typeof plain !== 'string' || Buffer.byteLength(plain) > MAX_BYTES) throw new Error();
    const raw: unknown = JSON.parse(plain);
    if (!exact(raw, ['version', 'scope', 'request']) || raw.version !== 1) throw new Error();
    const savedScope = parseScope(raw.scope); const request = parseRequest(raw.request);
    if (savedScope.serviceOrigin !== scope.serviceOrigin || savedScope.userId !== scope.userId || request.request_id !== requestId ||
        JSON.stringify({version: 1, scope: savedScope, request}) !== plain) throw new Error();
    return request;
  } catch {return fail('INVALID_RECORD');}
}
async function readResearchExisting(filename:string,scope:ExecutionJournalScope,requestId:string,protection:DeviceKeyProtection):Promise<ResearchJournalRecord|null>{
  let metadata;try{metadata=await lstat(filename);}catch(error){if(hasCode(error,'ENOENT'))return null;return fail('STORAGE_FAILED');}
  if(!metadata.isFile()||metadata.isSymbolicLink()||metadata.size<1||metadata.size>MAX_BYTES)fail('INVALID_RECORD');
  let bytes:Buffer;try{const handle=await open(filename,constants.O_RDWR|(constants.O_NOFOLLOW??0));try{const actual=await handle.stat();
    if(!actual.isFile()||actual.dev!==metadata.dev||actual.ino!==metadata.ino)throw new Error();const buffer=Buffer.alloc(MAX_BYTES+1);let size=0;
    while(size<buffer.length){const result=await handle.read(buffer,size,buffer.length-size,size);if(!result.bytesRead)break;size+=result.bytesRead;}
    if(!size||size>MAX_BYTES)throw new Error();bytes=buffer.subarray(0,size);await handle.sync();}finally{await handle.close();}}catch{return fail('STORAGE_FAILED');}
  let plain:string;try{plain=protection.decryptString(bytes);}catch{return fail('PROTECTION_FAILED');}
  try{if(typeof plain!=='string'||Buffer.byteLength(plain)>MAX_BYTES)throw new Error();const raw:unknown=JSON.parse(plain);
    if(!exact(raw,['version','scope','record'])||raw.version!==2)throw new Error();const savedScope=parseScope(raw.scope);const record=parseResearchRecord(raw.record);
    if(savedScope.serviceOrigin!==scope.serviceOrigin||savedScope.userId!==scope.userId||record.request.request_id!==requestId||
      JSON.stringify({version:2,scope:savedScope,record})!==plain)throw new Error();return record;}catch{return fail('INVALID_RECORD');}
}
async function serialized<T>(filename: string, action: () => Promise<T>): Promise<T> {
  const key = process.platform === 'win32' ? filename.toLowerCase() : filename;
  const result = (pendingFiles.get(key) ?? Promise.resolve()).then(action);
  const settled = result.then(() => undefined, () => undefined); pendingFiles.set(key, settled);
  void settled.then(() => {if (pendingFiles.get(key) === settled) pendingFiles.delete(key);});
  return result;
}

/** Trusted fixed main-process storage. Entries are never updated, replaced, or deleted. */
export function createExecutionJournal(options: {directory: string; protection: DeviceKeyProtection}): ExecutionJournal {
  if (typeof options.directory !== 'string' || !path.isAbsolute(options.directory) ||
      path.resolve(options.directory) === path.parse(options.directory).root) fail('STORAGE_FAILED');
  const directory = path.resolve(options.directory); const protection = options.protection;
  const prefix = (scope: ExecutionJournalScope) => createHash('sha256').update(JSON.stringify(scope)).digest('hex') + '-';
  const filename = (scope: ExecutionJournalScope, requestId: string) => path.join(directory, `${prefix(scope)}${requestId}.execution`);
  const researchFilename=(scope:ExecutionJournalScope,requestId:string)=>path.join(directory,`${prefix(scope)}${requestId}.research-execution`);
  return {
    async persist(inputScope, inputRequest) {
      // Snapshot both inputs before entering the shared file queue.
      const scope = parseScope(inputScope); const request = parseRequest(inputRequest); const target = filename(scope, request.request_id);
      function existingResult(existing: ExecutionOperation) {
        if (JSON.stringify(existing) !== JSON.stringify(request)) fail('CONFLICT');
        return {request: existing, created: false};
      }
      return serialized(target, async () => {
        requireProtection(protection); await directoryReady(directory, true);
        const existing = await readExisting(target, scope, request.request_id, protection);
        if (existing) return existingResult(existing);
        let bytes: Buffer;
        try {
          const encrypted = protection.encryptString(JSON.stringify({version: 1, scope, request}));
          if (!Buffer.isBuffer(encrypted) || !encrypted.length || encrypted.length > MAX_BYTES) throw new Error();
          bytes = Buffer.from(encrypted);
        } catch {return fail('PROTECTION_FAILED');}
        let handle;
        try {handle = await open(target, 'wx', 0o600);} catch (error) {
          if (hasCode(error, 'EEXIST')) {
            const concurrent = await readExisting(target, scope, request.request_id, protection);
            if (concurrent) return existingResult(concurrent);
          }
          return fail('STORAGE_FAILED');
        }
        try {
          try {await handle.writeFile(bytes); await handle.sync();} finally {await handle.close();}
        } catch {return fail('STORAGE_FAILED');} // Preserve any partial/unknown file for explicit recovery.
        return {request, created: true};
      });
    },
    async read(inputScope, inputId) {
      const scope = parseScope(inputScope); let requestId: string;
      try {requestId = deviceUuidSchema.parse(inputId);} catch {return fail('INVALID_RECORD');}
      const target = filename(scope, requestId);
      return serialized(target, async () => {
        requireProtection(protection); if (!await directoryReady(directory, false)) return null;
        return readExisting(target, scope, requestId, protection);
      });
    },
    async list(inputScope) {
      const scope = parseScope(inputScope); const start = prefix(scope);
      requireProtection(protection); if (!await directoryReady(directory, false)) return [];
      const ids: string[] = [];
      try {
        // Streaming enumeration bounds memory and rejects overflow instead of returning a partial list.
        for await (const entry of await opendir(directory)) {
          if (!entry.name.startsWith(start) || !entry.name.endsWith('.execution')) continue;
          const id = deviceUuidSchema.safeParse(entry.name.slice(start.length, -'.execution'.length));
          if (!id.success) fail('INVALID_RECORD');
          ids.push(id.data); if (ids.length > MAX_LIST_RECORDS) fail('LIMIT_EXCEEDED');
        }
      } catch (error) {if (error instanceof JournalError) throw error; return fail('STORAGE_FAILED');}
      const requests: ExecutionOperation[] = [];
      for (const id of ids.sort()) {
        const target = filename(scope, id);
        const request = await serialized(target, () => readExisting(target, scope, id, protection));
        if (!request) fail('STORAGE_FAILED');
        requests.push(request);
      }
      return requests;
    },
    async persistResearch(inputScope,inputRecord){
      const scope=parseScope(inputScope);const record=parseResearchRecord(inputRecord);const target=researchFilename(scope,record.request.request_id);
      function existingResult(existing:ResearchJournalRecord){if(JSON.stringify(existing)!==JSON.stringify(record))fail('CONFLICT');return {record:existing,created:false};}
      return serialized(target,async()=>{requireProtection(protection);await directoryReady(directory,true);const existing=await readResearchExisting(target,scope,record.request.request_id,protection);
        if(existing)return existingResult(existing);let bytes:Buffer;try{const encrypted=protection.encryptString(JSON.stringify({version:2,scope,record}));
          if(!Buffer.isBuffer(encrypted)||!encrypted.length||encrypted.length>MAX_BYTES)throw new Error();bytes=Buffer.from(encrypted);}catch{return fail('PROTECTION_FAILED');}
        let handle;try{handle=await open(target,'wx',0o600);}catch(error){if(hasCode(error,'EEXIST')){const concurrent=await readResearchExisting(target,scope,record.request.request_id,protection);if(concurrent)return existingResult(concurrent);}return fail('STORAGE_FAILED');}
        try{try{await handle.writeFile(bytes);await handle.sync();}finally{await handle.close();}}catch{return fail('STORAGE_FAILED');}return {record,created:true};});
    },
    async readResearch(inputScope,inputId){const scope=parseScope(inputScope);let requestId:string;try{requestId=deviceUuidSchema.parse(inputId);}catch{return fail('INVALID_RECORD');}
      const target=researchFilename(scope,requestId);return serialized(target,async()=>{requireProtection(protection);if(!await directoryReady(directory,false))return null;
        return readResearchExisting(target,scope,requestId,protection);});},
    async listResearch(inputScope){const scope=parseScope(inputScope);const start=prefix(scope);requireProtection(protection);if(!await directoryReady(directory,false))return [];
      const ids:string[]=[];try{for await(const entry of await opendir(directory)){if(!entry.name.startsWith(start)||!entry.name.endsWith('.research-execution'))continue;
        const id=deviceUuidSchema.safeParse(entry.name.slice(start.length,-'.research-execution'.length));if(!id.success)fail('INVALID_RECORD');ids.push(id.data);if(ids.length>MAX_LIST_RECORDS)fail('LIMIT_EXCEEDED');}}
      catch(error){if(error instanceof JournalError)throw error;return fail('STORAGE_FAILED');}const records:ResearchJournalRecord[]=[];
      for(const id of ids.sort()){const target=researchFilename(scope,id);const record=await serialized(target,()=>readResearchExisting(target,scope,id,protection));if(!record)fail('STORAGE_FAILED');records.push(record);}return records;},
  };
}
