import {afterEach, describe, expect, it, vi} from 'vitest';
import {createCipheriv, createDecipheriv, createHash, randomBytes} from 'node:crypto';
import {mkdir, mkdtemp, readdir, readFile, rename, rm, symlink, writeFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createCandidateJournal, type CandidateBatchKey, type CandidateJournalScope} from '../src/main/candidateJournal';
import type {CandidateSubmission} from '../src/shared/candidateSubmission';
import type {DeviceKeyProtection} from '../src/main/deviceKeyVault';
import {id, recoveryBatch} from './candidateRecoveryFixtures';

const faults = vi.hoisted(() => ({syncCalls: 0, failSyncAt: 0, partialWrite: false, replaceOnOpen: false}));
vi.mock('node:fs/promises', async importOriginal => {
  const original = await importOriginal<typeof import('node:fs/promises')>();
  return {...original, open: async (...args: Parameters<typeof original.open>) => {
    if (faults.replaceOnOpen) {
      faults.replaceOnOpen = false;
      const filename = String(args[0]);
      await original.rename(filename, filename + '.previous');
      await original.copyFile(filename + '.previous', filename);
    }
    const handle = await original.open(...args);
    const sync = handle.sync.bind(handle); const write = handle.writeFile.bind(handle);
    handle.sync = async () => {if (++faults.syncCalls === faults.failSyncAt) throw new Error('/private/sync'); return sync();};
    handle.writeFile = async (data, options) => {
      if (faults.partialWrite) {faults.partialWrite = false; await write(Buffer.from(data as Uint8Array).subarray(0, 10)); throw new Error('/private/write');}
      return write(data, options);
    };
    return handle;
  }};
});

const scope: CandidateJournalScope = {serviceOrigin: 'https://service.example', userId: '企业用户😀'};
const roots: string[] = [];
const key = (batch = recoveryBatch()): CandidateBatchKey => ({platformRunId: batch.execution.platform_run_id, requestId: batch.request_id});
const digest = (value: unknown) => createHash('sha256').update(JSON.stringify(value)).digest('hex');
function protection(): DeviceKeyProtection {
  const secret = randomBytes(32);
  return {isEncryptionAvailable: () => true,
    encryptString(plain) {
      const iv = randomBytes(12); const cipher = createCipheriv('aes-256-gcm', secret, iv);
      return Buffer.concat([iv, cipher.update(plain, 'utf8'), cipher.final(), cipher.getAuthTag()]);
    },
    decryptString(bytes) {
      const cipher = createDecipheriv('aes-256-gcm', secret, bytes.subarray(0, 12)); cipher.setAuthTag(bytes.subarray(-16));
      return Buffer.concat([cipher.update(bytes.subarray(12, -16)), cipher.final()]).toString('utf8');
    }};
}
async function setup() {
  const root = await mkdtemp(path.join(os.tmpdir(), 'yike-candidate-journal-')); roots.push(root);
  const options = {directory: path.join(root, 'journal'), protection: protection()};
  return {...options, root, journal: createCandidateJournal(options)};
}
async function oneFile(directory: string) {
  const files = await readdir(directory); expect(files).toHaveLength(1);
  expect(files[0]).toMatch(/^[0-9a-f]{64}-[0-9a-f]{64}\.candidate$/);
  return path.join(directory, files[0]);
}
afterEach(async () => {
  vi.restoreAllMocks(); Object.assign(faults, {syncCalls: 0, failSyncAt: 0, partialWrite: false, replaceOnOpen: false});
  for (const directory of roots.splice(0)) {
    const target = path.resolve(directory);
    if (path.dirname(target) !== path.resolve(os.tmpdir()) || !path.basename(target).startsWith('yike-candidate-journal-')) throw new Error('UNSAFE_TEST_CLEANUP');
    await rm(target, {recursive: true, force: true});
  }
});

describe('protected immutable candidate batch journal', () => {
  it('does not create storage for a missing read or list', async () => {
    const f = await setup(); expect(await f.journal.read(scope, key())).toBeNull(); expect(await f.journal.list(scope)).toEqual([]);
    expect(await readdir(f.root)).toEqual([]);
  });
  it('recovers exact Unicode, nulls and ordered records after reconstruction with only ciphertext on disk', async () => {
    const f = await setup(); const batch = recoveryBatch(); batch.records.push({...batch.records[0], body: '第二条'});
    expect(await f.journal.persist(scope, batch)).toEqual({batch, created: true});
    const filename = await oneFile(f.directory); const bytes = await readFile(filename);
    for (const secret of [scope.userId, batch.request_id, batch.records[0].body]) expect(bytes.includes(Buffer.from(secret))).toBe(false);
    expect(path.basename(filename)).toBe(`${digest(scope)}-${digest(key(batch))}.candidate`);
    expect(JSON.parse(f.protection.decryptString(bytes))).toEqual({version: 1, scope, key: key(batch), batch});
    const other = createCandidateJournal(f); const saved = await other.read(scope, key(batch));
    expect(saved).toEqual(batch); expect(await other.list(scope)).toEqual([key(batch)]);
    expect(Object.isFrozen(saved)).toBe(true); expect(Object.isFrozen(saved!.execution)).toBe(true);
    expect(Object.isFrozen(saved!.records)).toBe(true); expect(Object.isFrozen(saved!.records[0])).toBe(true);
    expect(await other.persist(scope, batch)).toEqual({batch, created: false}); expect(await readFile(filename)).toEqual(bytes);
  });
  it('normalizes defaults and property ordering but not text or array order', async () => {
    const f = await setup(); const batch = recoveryBatch(); batch.records[0] = {...batch.records[0], kind: 'COMMENT', external_comment_id: 'child', parent: {external_comment_id: 'parent', body: null, author_public_id: null, published_at: null, public_url: null}};
    const raw = Object.fromEntries(Object.entries(structuredClone(batch)).reverse()) as CandidateSubmission;
    delete (raw.execution as Partial<typeof raw.execution>).connection_version;
    delete (raw.records[0].parent as Partial<NonNullable<typeof raw.records[0]['parent']>>).body;
    const result = await f.journal.persist(scope, raw); expect(result.batch).toEqual(batch);
    expect(Object.isFrozen(result.batch.records[0].parent)).toBe(true);
    expect(await f.journal.persist(scope, batch)).toEqual({batch, created: false});
    await expect(f.journal.persist(scope, {...batch, records: [{...batch.records[0], body: batch.records[0].body.trim()}]})).rejects.toThrow('CANDIDATE_JOURNAL_CONFLICT');
  });
  it('same-key conflicts preserve original bytes across concurrent factories', async () => {
    const f = await setup(); const batch = recoveryBatch(); const other = createCandidateJournal({...f, directory: path.join(f.directory, '.')});
    const results = await Promise.all(Array.from({length: 12}, (_, i) => (i % 2 ? other : f.journal).persist(scope, batch)));
    expect(results.filter(result => result.created)).toHaveLength(1);
    const filename = await oneFile(f.directory); const bytes = await readFile(filename);
    await expect(other.persist(scope, {...batch, records: []})).rejects.toThrow(/^CANDIDATE_JOURNAL_CONFLICT$/);
    expect(await readFile(filename)).toEqual(bytes);
  });
  it('distinguishes platforms, users, origins and case-sensitive opaque A/a request keys', async () => {
    const f = await setup(); const batch = recoveryBatch();
    const variants = [batch, {...batch, execution: {...batch.execution, platform_run_id: id(80)}}, {...batch, request_id: 'A'}, {...batch, request_id: 'a'}];
    for (const item of variants) expect((await f.journal.persist(scope, item)).created).toBe(true);
    for (const item of variants) expect(await createCandidateJournal(f).read(scope, key(item))).toEqual(item);
    const scopes = [{...scope, userId: 'other'}, {...scope, serviceOrigin: 'https://other.example'}];
    for (const value of scopes) {await f.journal.persist(value, batch); expect(await f.journal.list(value)).toEqual([key(batch)]);}
    expect(await f.journal.list(scope)).toEqual(expect.arrayContaining(variants.map(item => key(item))));
    expect(await readdir(f.directory)).toHaveLength(6);
  });
  it('detaches and deeply freezes inputs before waiting in the cross-factory queue', async () => {
    const f = await setup(); const batch = recoveryBatch(); const expected = structuredClone(batch); const suppliedScope = {...scope};
    const first = f.journal.persist(scope, batch); const next = createCandidateJournal(f).persist(suppliedScope, batch);
    suppliedScope.userId = 'changed'; batch.request_id = 'changed'; batch.execution.platform_run_id = id(50); batch.records[0].body = 'changed';
    expect(await Promise.all([first, next])).toEqual([{batch: expected, created: true}, {batch: expected, created: false}]);
    const suppliedKey = key(expected); const reading = f.journal.read(scope, suppliedKey); suppliedKey.requestId = 'changed';
    expect(await reading).toEqual(expected);
  });
  it.each([null, {...scope, private: 'secret'}, {...scope, userId: '\ud800'}, {...scope, userId: ''}, {...scope, userId: 'user\n'}, {...scope, serviceOrigin: 'https://service.example/'}, {...scope, serviceOrigin: 'http://public.example'}])('rejects invalid scope before disk access %#', async input => {
    const f = await setup(); await expect(f.journal.persist(input as CandidateJournalScope, recoveryBatch())).rejects.toThrow(/^CANDIDATE_JOURNAL_INVALID_SCOPE$/);
    await expect(f.journal.read(input as CandidateJournalScope, key())).rejects.toThrow(/^CANDIDATE_JOURNAL_INVALID_SCOPE$/);
    await expect(f.journal.list(input as CandidateJournalScope)).rejects.toThrow(/^CANDIDATE_JOURNAL_INVALID_SCOPE$/); expect(await readdir(f.root)).toEqual([]);
  });
  it.each([{...key(), requestId: '../private'}, {...key(), platformRunId: 'opaque'}, {...key(), extra: true}])('rejects invalid keys before disk access %#', async input => {
    const f = await setup(); await expect(f.journal.read(scope, input)).rejects.toThrow(/^CANDIDATE_JOURNAL_INVALID_RECORD$/); expect(await readdir(f.root)).toEqual([]);
  });
  it('rejects batches with invalid platform UUIDs or unexpected fields', async () => {
    const f = await setup(); const batch = recoveryBatch();
    await expect(f.journal.persist(scope, {...batch, execution: {...batch.execution, platform_run_id: 'opaque'}})).rejects.toThrow(/^CANDIDATE_JOURNAL_INVALID_RECORD$/);
    await expect(f.journal.persist(scope, {...batch, signature: 'secret'} as CandidateSubmission)).rejects.toThrow(/^CANDIDATE_JOURNAL_INVALID_RECORD$/);
    expect(await readdir(f.root)).toEqual([]);
  });
  it('fails closed without touching disk when protection is unavailable', async () => {
    const f = await setup(); vi.spyOn(f.protection, 'isEncryptionAvailable').mockReturnValue(false);
    await expect(f.journal.persist(scope, recoveryBatch())).rejects.toThrow(/^CANDIDATE_JOURNAL_PROTECTION_UNAVAILABLE$/);
    await expect(f.journal.read(scope, key())).rejects.toThrow(/^CANDIDATE_JOURNAL_PROTECTION_UNAVAILABLE$/);
    await expect(f.journal.list(scope)).rejects.toThrow(/^CANDIDATE_JOURNAL_PROTECTION_UNAVAILABLE$/); expect(await readdir(f.root)).toEqual([]);
  });
  it.each(['throw', 'oversize'])('never writes plaintext on encryption failure: %s', async mode => {
    const f = await setup(); vi.spyOn(f.protection, 'encryptString').mockImplementation(() => {if (mode === 'throw') throw new Error('private'); return Buffer.alloc(8 * 1024 * 1024 + 1);});
    await expect(f.journal.persist(scope, recoveryBatch())).rejects.toThrow(/^CANDIDATE_JOURNAL_PROTECTION_FAILED$/); expect(await readdir(f.directory)).toEqual([]);
  });
  it('checks actual UTF-8 signed envelope bytes before creating storage', async () => {
    const f = await setup(); const batch = recoveryBatch(); batch.records = Array.from({length: 100}, () => ({...batch.records[0], body: '😀'.repeat(12000)}));
    expect(Buffer.byteLength(JSON.stringify({batch, signature: 'A'.repeat(86)}))).toBeGreaterThan(4 * 1024 * 1024);
    await expect(f.journal.persist(scope, batch)).rejects.toThrow(/^CANDIDATE_JOURNAL_LIMIT_EXCEEDED$/); expect(await readdir(f.root)).toEqual([]);
  });
  it.each(['empty', 'oversized', 'ciphertext', 'scope', 'key', 'batchKey', 'extra', 'missingNull', 'plainOversize'])('retains corrupt or replaced %s files without rebuilding', async mode => {
    const f = await setup(); const batch = recoveryBatch(); await f.journal.persist(scope, batch); const filename = await oneFile(f.directory);
    const record: any = {version: 1, scope: {...scope}, key: key(batch), batch: structuredClone(batch)};
    if (mode === 'scope') record.scope.userId = 'other'; if (mode === 'key') record.key.requestId = 'other'; if (mode === 'batchKey') record.batch.request_id = 'other';
    if (mode === 'extra') record.signature = 'secret'; if (mode === 'missingNull') delete record.batch.execution.connection_version;
    const bytes = mode === 'empty' ? Buffer.alloc(0) : mode === 'oversized' ? Buffer.alloc(8 * 1024 * 1024 + 1) : mode === 'ciphertext' ? Buffer.from('corrupt') : f.protection.encryptString(mode === 'plainOversize' ? ' '.repeat(4 * 1024 * 1024 + 16385) : JSON.stringify(record));
    await writeFile(filename, bytes);
    await expect(f.journal.persist(scope, batch)).rejects.toThrow(/^CANDIDATE_JOURNAL_(INVALID_RECORD|PROTECTION_FAILED)$/);
    await expect(f.journal.list(scope)).rejects.toThrow(/^CANDIDATE_JOURNAL_(INVALID_RECORD|PROTECTION_FAILED)$/); expect((await readFile(filename)).equals(bytes)).toBe(true);
  });
  it('rejects a valid encrypted batch relocated under the wrong hash', async () => {
    const f = await setup(); await f.journal.persist(scope, recoveryBatch()); const filename = await oneFile(f.directory);
    await rename(filename, path.join(f.directory, `${digest(scope)}-${'a'.repeat(64)}.candidate`));
    await expect(f.journal.list(scope)).rejects.toThrow(/^CANDIDATE_JOURNAL_INVALID_RECORD$/);
  });
  it('detects a file replacement between lstat and open', async () => {
    const f = await setup(); await f.journal.persist(scope, recoveryBatch()); faults.replaceOnOpen = true;
    await expect(f.journal.read(scope, key())).rejects.toThrow(/^CANDIDATE_JOURNAL_STORAGE_FAILED$/);
    expect(await readdir(f.directory)).toHaveLength(2);
  });
  it('preserves partial writes and refuses to replace them', async () => {
    const f = await setup(); faults.partialWrite = true;
    await expect(f.journal.persist(scope, recoveryBatch())).rejects.toThrow(/^CANDIDATE_JOURNAL_STORAGE_FAILED$/);
    const filename = await oneFile(f.directory); expect(await readFile(filename)).toHaveLength(10);
    await expect(f.journal.persist(scope, recoveryBatch())).rejects.toThrow(/^CANDIDATE_JOURNAL_PROTECTION_FAILED$/); expect(await readFile(filename)).toHaveLength(10);
  });
  it('requires a successful sync before accepting full bytes left by a failed initial sync', async () => {
    const f = await setup(); faults.failSyncAt = 1;
    await expect(f.journal.persist(scope, recoveryBatch())).rejects.toThrow(/^CANDIDATE_JOURNAL_STORAGE_FAILED$/);
    faults.failSyncAt = 2; await expect(createCandidateJournal(f).read(scope, key())).rejects.toThrow(/^CANDIDATE_JOURNAL_STORAGE_FAILED$/);
    expect(await f.journal.persist(scope, recoveryBatch())).toMatchObject({created: false});
  });
  it('rejects symlink record and storage directories without following them', async () => {
    const f = await setup(); await f.journal.persist(scope, recoveryBatch()); const filename = await oneFile(f.directory); await rm(filename);
    const target = path.join(f.root, 'target'); await mkdir(target); await symlink(target, filename, process.platform === 'win32' ? 'junction' : 'dir');
    await expect(f.journal.read(scope, key())).rejects.toThrow(/^CANDIDATE_JOURNAL_INVALID_RECORD$/);
    const link = path.join(f.root, 'linked'); await symlink(target, link, process.platform === 'win32' ? 'junction' : 'dir');
    await expect(createCandidateJournal({...f, directory: link}).persist(scope, recoveryBatch())).rejects.toThrow(/^CANDIDATE_JOURNAL_STORAGE_FAILED$/); expect(await readdir(target)).toEqual([]);
  });
  it('fails the entire list above 1000 scoped names rather than truncating or decoding aggregate bodies', async () => {
    const f = await setup(); await f.journal.persist(scope, recoveryBatch());
    await Promise.all(Array.from({length: 1000}, (_, index) => writeFile(path.join(f.directory, `${digest(scope)}-${digest(index)}.candidate`), 'unread')));
    await expect(f.journal.list(scope)).rejects.toThrow(/^CANDIDATE_JOURNAL_LIMIT_EXCEEDED$/); expect(await readdir(f.directory)).toHaveLength(1001);
  });
});
