import {afterEach, describe, expect, it, vi} from 'vitest';
import {createCipheriv, createDecipheriv, randomBytes, randomUUID} from 'node:crypto';
import {mkdtemp, readdir, readFile, writeFile, mkdir, rm, symlink} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createExecutionJournal, type ExecutionJournalScope} from '../src/main/executionJournal';
import {executionOperationSchema, type ExecutionOperation} from '../src/shared/executionOperation';
import type {DeviceKeyProtection} from '../src/main/deviceKeyVault';

const faults = vi.hoisted(() => ({syncCalls: 0, failSyncAt: 0, partialWrite: false}));
vi.mock('node:fs/promises', async importOriginal => {
  const original = await importOriginal<typeof import('node:fs/promises')>();
  return {...original, open: async (...args: Parameters<typeof original.open>) => {
    const handle = await original.open(...args);
    const sync = handle.sync.bind(handle);
    const write = handle.writeFile.bind(handle);
    handle.sync = async () => {if (++faults.syncCalls === faults.failSyncAt) throw new Error('/private/sync'); return sync();};
    handle.writeFile = async (data, options) => {
      if (faults.partialWrite) {faults.partialWrite = false; await write(Buffer.from(data as Uint8Array).subarray(0, 10)); throw new Error('/private/write');}
      return write(data, options);
    };
    return handle;
  }};
});

const scope: ExecutionJournalScope = {serviceOrigin: 'https://service.example', userId: '企业用户😀'};
const roots: string[] = [];
function protection(): DeviceKeyProtection {
  const secret = randomBytes(32);
  return {
    isEncryptionAvailable: () => true,
    encryptString(plain) {
      const iv = randomBytes(12); const cipher = createCipheriv('aes-256-gcm', secret, iv);
      return Buffer.concat([iv, cipher.update(plain, 'utf8'), cipher.final(), cipher.getAuthTag()]);
    },
    decryptString(bytes) {
      const cipher = createDecipheriv('aes-256-gcm', secret, bytes.subarray(0, 12)); cipher.setAuthTag(bytes.subarray(-16));
      return Buffer.concat([cipher.update(bytes.subarray(12, -16)), cipher.final()]).toString('utf8');
    },
  };
}
function request(request_id = randomUUID()): ExecutionOperation {
  return executionOperationSchema.parse({schema_version: 'execution-runtime-v1', request_id, operation: 'START', device_id: '00000000-0000-0000-0000-000000000002', credential_version: 1,
    profile_version_id: 'private-profile', strategy_version_id: 'private-strategy', configuration_sha256: 'a'.repeat(64), targets: [{platform: 'PUBLIC_WEB', access_mode: 'PUBLIC_ANONYMOUS', connection_id: null}]});
}
async function setup() {
  const root = await mkdtemp(path.join(os.tmpdir(), 'yike-execution-journal-')); roots.push(root);
  const options = {directory: path.join(root, 'journal'), protection: protection()};
  return {...options, root, journal: createExecutionJournal(options)};
}
async function oneFile(directory: string) {
  const files = await readdir(directory); expect(files).toHaveLength(1);
  expect(files[0]).toMatch(/^[0-9a-f]{64}-[0-9a-f-]{36}\.execution$/);
  return path.join(directory, files[0]);
}
afterEach(async () => {
  vi.restoreAllMocks(); Object.assign(faults, {syncCalls: 0, failSyncAt: 0, partialWrite: false});
  for (const directory of roots.splice(0)) {
    const target = path.resolve(directory);
    if (path.dirname(target) !== path.resolve(os.tmpdir()) || !path.basename(target).startsWith('yike-execution-journal-')) throw new Error('UNSAFE_TEST_CLEANUP');
    await rm(target, {recursive: true, force: true});
  }
});

describe('immutable protected execution operation journal', () => {
  it('missing read/list perform no directory or file creation', async () => {
    const f = await setup();
    await expect(f.journal.read(scope, randomUUID())).resolves.toBeNull();
    await expect(f.journal.list(scope)).resolves.toEqual([]);
    expect(await readdir(f.root)).toEqual([]);
  });
  it('persists only encrypted version/scope/request and recovers the exact canonical request after reconstruction', async () => {
    const f = await setup(); const input = request();
    await expect(f.journal.persist(scope, input)).resolves.toEqual({request: input, created: true});
    const bytes = await readFile(await oneFile(f.directory));
    for (const secret of [scope.userId, input.request_id, input.profile_version_id!, input.strategy_version_id!]) expect(bytes.includes(Buffer.from(secret))).toBe(false);
    expect(JSON.parse(f.protection.decryptString(bytes))).toEqual({version: 1, scope, request: input});
    const other = createExecutionJournal(f);
    await expect(other.read(scope, input.request_id)).resolves.toEqual(input);
    await expect(other.persist(scope, input)).resolves.toEqual({request: input, created: false});
    const saved = (await other.list(scope))[0]; expect(saved).toEqual(input);
    expect(Object.isFrozen(saved)).toBe(true); expect(Object.isFrozen(saved.targets)).toBe(true); expect(Object.isFrozen(saved.targets![0])).toBe(true);
    expect(await readFile(await oneFile(f.directory))).toEqual(bytes);
  });
  it('normalizes omitted null defaults and input key order into the same immutable request', async () => {
    const f = await setup(); const input = request();
    await expect(f.journal.persist(scope, input)).resolves.toMatchObject({created: true});
    const changed = Object.fromEntries(Object.entries(input).reverse()) as ExecutionOperation;
    delete (changed as Partial<ExecutionOperation>).task_id;
    await expect(f.journal.persist(scope, changed)).resolves.toEqual({request: input, created: false});
  });
  it('same scope/UUID content conflict never replaces the original bytes', async () => {
    const f = await setup(); const input = request();
    await expect(f.journal.persist(scope, input)).resolves.toMatchObject({created: true});
    const filename = await oneFile(f.directory); const bytes = await readFile(filename);
    await expect(f.journal.persist(scope, {...input, configuration_sha256: 'b'.repeat(64)})).rejects.toThrow(/^EXECUTION_JOURNAL_CONFLICT$/);
    expect(await readFile(filename)).toEqual(bytes); expect(await f.journal.read(scope, input.request_id)).toEqual(input);
  });
  it('serializes same-file concurrent persistence across factories into one creator', async () => {
    const f = await setup(); const input = request(); const other = createExecutionJournal({...f, directory: path.join(f.directory, '.')});
    const results = await Promise.all(Array.from({length: 16}, (_, i) => (i % 2 ? other : f.journal).persist(scope, input)));
    expect(results.filter(result => result.created)).toHaveLength(1); expect(results.every(result => JSON.stringify(result.request) === JSON.stringify(input))).toBe(true);
    await oneFile(f.directory);
  });
  it('concurrent conflicting requests permit exactly one immutable winner', async () => {
    const f = await setup(); const input = request();
    const results = await Promise.allSettled([f.journal.persist(scope, input), createExecutionJournal(f).persist(scope, {...input, credential_version: 2})]);
    expect(results.filter(result => result.status === 'fulfilled')).toHaveLength(1);
    const rejection = results.find(result => result.status === 'rejected');
    expect(rejection?.status === 'rejected' && rejection.reason.message).toBe('EXECUTION_JOURNAL_CONFLICT');
    expect(await f.journal.read(scope, input.request_id)).toEqual(input);
  });
  it('isolates equal UUIDs across users and origins and lists only the requested scope', async () => {
    const f = await setup(); const input = request();
    const scopes = [scope, {...scope, userId: '其他用户'}, {...scope, serviceOrigin: 'https://other.example'}];
    for (const [index, value] of scopes.entries()) await expect(f.journal.persist(value, {...input, credential_version: index + 1})).resolves.toMatchObject({created: true});
    expect(await readdir(f.directory)).toHaveLength(3);
    for (const [index, value] of scopes.entries()) expect(await f.journal.list(value)).toEqual([{...input, credential_version: index + 1}]);
    expect(await f.journal.list({...scope, userId: 'missing'})).toEqual([]);
  });
  it('snapshots caller scope and nested request before awaiting storage', async () => {
    const f = await setup(); const suppliedScope = {...scope}; const input = request(); const original = structuredClone(input);
    const pending = f.journal.persist(suppliedScope, input); suppliedScope.userId = 'changed'; input.targets![0].platform = 'DOUYIN'; input.request_id = randomUUID();
    await expect(pending).resolves.toEqual({request: original, created: true});
    const readScope = {...scope}; const reading = f.journal.read(readScope, original.request_id); readScope.userId = 'changed';
    expect(await reading).toEqual(original);
    const listScope = {...scope}; const listing = f.journal.list(listScope); listScope.userId = 'changed'; expect(await listing).toEqual([original]);
  });
  it.each([null, {...scope, private: 'secret'}, {...scope, userId: ''}, {...scope, userId: '\ud800'}, {...scope, userId: 'bad\nuser'}, {...scope, serviceOrigin: 'https://service.example/'}, {...scope, serviceOrigin: 'http://public.example'}])('rejects invalid scope before any filesystem work %#', async value => {
    const f = await setup();
    await expect(f.journal.persist(value as ExecutionJournalScope, request())).rejects.toThrow(/^EXECUTION_JOURNAL_INVALID_SCOPE$/);
    await expect(f.journal.read(value as ExecutionJournalScope, randomUUID())).rejects.toThrow(/^EXECUTION_JOURNAL_INVALID_SCOPE$/);
    await expect(f.journal.list(value as ExecutionJournalScope)).rejects.toThrow(/^EXECUTION_JOURNAL_INVALID_SCOPE$/);
    expect(await readdir(f.root)).toEqual([]);
  });
  it('rejects invalid requests and traversal UUIDs before filesystem work', async () => {
    const f = await setup();
    await expect(f.journal.persist(scope, {...request(), signature: 'secret'} as ExecutionOperation)).rejects.toThrow(/^EXECUTION_JOURNAL_INVALID_RECORD$/);
    await expect(f.journal.read(scope, '../private')).rejects.toThrow(/^EXECUTION_JOURNAL_INVALID_RECORD$/);
    expect(await readdir(f.root)).toEqual([]);
  });
  it('fails closed with no directory creation when OS protection is unavailable', async () => {
    const f = await setup(); vi.spyOn(f.protection, 'isEncryptionAvailable').mockReturnValue(false);
    await expect(f.journal.persist(scope, request())).rejects.toThrow(/^EXECUTION_JOURNAL_PROTECTION_UNAVAILABLE$/);
    await expect(f.journal.read(scope, randomUUID())).rejects.toThrow(/^EXECUTION_JOURNAL_PROTECTION_UNAVAILABLE$/);
    await expect(f.journal.list(scope)).rejects.toThrow(/^EXECUTION_JOURNAL_PROTECTION_UNAVAILABLE$/);
    expect(await readdir(f.root)).toEqual([]);
  });
  it('does not fall back to plaintext when encryption fails', async () => {
    const f = await setup(); vi.spyOn(f.protection, 'encryptString').mockImplementation(() => {throw new Error('/private/OS');});
    await expect(f.journal.persist(scope, request())).rejects.toThrow(/^EXECUTION_JOURNAL_PROTECTION_FAILED$/);
    expect(await readdir(f.directory)).toEqual([]);
  });
  it.each(['empty', 'oversized', 'ciphertext', 'scope', 'requestId', 'extra', 'missingNull', 'signature'])('preserves corrupt or mismatched %s without rebuilding', async mode => {
    const f = await setup(); const input = request(); await expect(f.journal.persist(scope, input)).resolves.toMatchObject({created: true});
    const filename = await oneFile(f.directory); const record: any = {version: 1, scope: {...scope}, request: {...input}};
    if (mode === 'scope') record.scope.userId = 'other'; if (mode === 'requestId') record.request.request_id = randomUUID();
    if (mode === 'extra') record.sessionId = 'secret'; if (mode === 'missingNull') delete record.request.task_id;
    if (mode === 'signature') record.request.signature = 'secret';
    const bytes = mode === 'empty' ? Buffer.alloc(0) : mode === 'oversized' ? Buffer.alloc(65_537, 1) : mode === 'ciphertext' ? Buffer.from('corrupt') : f.protection.encryptString(JSON.stringify(record));
    await writeFile(filename, bytes);
    await expect(f.journal.persist(scope, input)).rejects.toThrow(/^EXECUTION_JOURNAL_(INVALID_RECORD|PROTECTION_FAILED)$/);
    await expect(f.journal.list(scope)).rejects.toThrow(/^EXECUTION_JOURNAL_(INVALID_RECORD|PROTECTION_FAILED)$/);
    expect(await readFile(filename)).toEqual(bytes);
  });
  it('preserves partial initial writes and refuses to overwrite them', async () => {
    const f = await setup(); const input = request(); faults.partialWrite = true;
    await expect(f.journal.persist(scope, input)).rejects.toThrow(/^EXECUTION_JOURNAL_STORAGE_FAILED$/);
    const filename = await oneFile(f.directory); expect(await readFile(filename)).toHaveLength(10);
    await expect(f.journal.persist(scope, input)).rejects.toThrow(/^EXECUTION_JOURNAL_PROTECTION_FAILED$/);
    expect(await readFile(filename)).toHaveLength(10);
  });
  it('failed-sync full bytes are recoverable only after a later existing-file sync succeeds', async () => {
    const f = await setup(); const input = request(); faults.failSyncAt = 1;
    await expect(f.journal.persist(scope, input)).rejects.toThrow(/^EXECUTION_JOURNAL_STORAGE_FAILED$/);
    const filename = await oneFile(f.directory); const bytes = await readFile(filename);
    faults.failSyncAt = 2; await expect(createExecutionJournal(f).read(scope, input.request_id)).rejects.toThrow(/^EXECUTION_JOURNAL_STORAGE_FAILED$/);
    await expect(f.journal.persist(scope, input)).resolves.toEqual({request: input, created: false});
    expect(faults.syncCalls).toBe(3); expect(await readFile(filename)).toEqual(bytes);
  });
  it('rejects a directory at the record path and a symlink journal directory', async () => {
    const f = await setup(); const input = request(); await expect(f.journal.persist(scope, input)).resolves.toMatchObject({created: true});
    const filename = await oneFile(f.directory); await rm(filename); await mkdir(filename);
    await expect(f.journal.read(scope, input.request_id)).rejects.toThrow(/^EXECUTION_JOURNAL_INVALID_RECORD$/);
    const target = path.join(f.root, 'target'); const link = path.join(f.root, 'linked'); await mkdir(target);
    await symlink(target, link, process.platform === 'win32' ? 'junction' : 'dir');
    await expect(createExecutionJournal({...f, directory: link}).persist(scope, request())).rejects.toThrow(/^EXECUTION_JOURNAL_STORAGE_FAILED$/);
    expect(await readdir(target)).toEqual([]);
  });
  it('list reports more than 1000 matching records as a whole failure, never truncation', async () => {
    const f = await setup(); const input = request(); await expect(f.journal.persist(scope, input)).resolves.toMatchObject({created: true});
    const filename = await oneFile(f.directory); const prefix = path.basename(filename).slice(0, 65);
    await Promise.all(Array.from({length: 1000}, () => writeFile(path.join(f.directory, `${prefix}${randomUUID()}.execution`), Buffer.from('unread'))));
    await expect(f.journal.list(scope)).rejects.toThrow(/^EXECUTION_JOURNAL_LIMIT_EXCEEDED$/);
    expect(await readdir(f.directory)).toHaveLength(1001);
  });
  it.each(['relative', path.parse(process.cwd()).root])('rejects unsafe directory %s', directory => {
    expect(() => createExecutionJournal({directory, protection: protection()})).toThrow(/^EXECUTION_JOURNAL_STORAGE_FAILED$/);
  });
});
