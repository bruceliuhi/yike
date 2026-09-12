import {createCipheriv, createDecipheriv, randomBytes, randomUUID} from 'node:crypto';
import {spawn} from 'node:child_process';
import {existsSync} from 'node:fs';
import {mkdtemp, mkdir, readdir, readFile, writeFile, rm, symlink} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {afterEach, describe, expect, it, vi} from 'vitest';
import type {DeviceKeyProtection} from '../src/main/deviceKeyVault';

const faults = vi.hoisted(() => ({partialWrite: false, failSync: false, denyCreate: false}));
vi.mock('node:fs/promises', async importOriginal => {
  const original = await importOriginal<typeof import('node:fs/promises')>();
  return {...original, open: async (...args: Parameters<typeof original.open>) => {
    if (faults.denyCreate && args[1] === 'wx') throw Object.assign(new Error('/private/storage'), {code: 'EACCES'});
    const handle = await original.open(...args);
    const write = handle.writeFile.bind(handle); const sync = handle.sync.bind(handle);
    handle.writeFile = async (data, options) => {
      if (faults.partialWrite) {faults.partialWrite = false; await write(Buffer.from(data as Uint8Array).subarray(0, 10)); throw new Error('/private/write');}
      return write(data, options);
    };
    handle.sync = async () => {if (faults.failSync) throw new Error('/private/sync'); return sync();};
    return handle;
  }};
});

const modulePath = fileURLToPath(new URL('../src/main/outreachConsumptionJournal.ts', import.meta.url));
const scope = {serviceOrigin: 'https://service.example', userId: '企业用户😀', tenantId: 'tenant-1'};
const roots: string[] = [];
function protection(secret = randomBytes(32)): DeviceKeyProtection {
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
function grant() {return {requestId: randomUUID(), claimId: randomUUID(), contextSha256: 'a'.repeat(64), deviceId: randomUUID()};}
async function setup() {
  expect(existsSync(modulePath), 'persistent outreach consumption implementation exists').toBe(true);
  const {createOutreachConsumptionJournal} = await import('../src/main/outreachConsumptionJournal');
  const root = await mkdtemp(path.join(os.tmpdir(), 'yike-outreach-consumption-')); roots.push(root);
  const options = {directory: path.join(root, 'consumption'), protection: protection()};
  return {...options, root, create: createOutreachConsumptionJournal, journal: createOutreachConsumptionJournal(options)};
}
async function oneFile(directory: string) {
  const names = await readdir(directory); expect(names).toHaveLength(1);
  expect(names[0]).toMatch(/^[0-9a-f]{64}\.consumed$/);
  return path.join(directory, names[0]);
}
afterEach(async () => {
  vi.restoreAllMocks(); Object.assign(faults, {partialWrite: false, failSync: false, denyCreate: false});
  for (const directory of roots.splice(0)) {
    if (path.dirname(directory) !== os.tmpdir() || !path.basename(directory).startsWith('yike-outreach-consumption-')) throw new Error('UNSAFE_TEST_CLEANUP');
    await rm(directory, {recursive: true, force: true});
  }
});

describe('immutable local outreach consumption', () => {
  it('consumes once and never reissues permission after reconstruction', async () => {
    const f = await setup(); const input = grant();
    expect(await f.journal.consumed(scope, input.requestId)).toBe(false); expect(await readdir(f.root)).toEqual([]);
    expect(await f.journal.consume(scope, input)).toEqual({created: true});
    const bytes = await readFile(await oneFile(f.directory));
    expect(JSON.parse(f.protection.decryptString(bytes))).toEqual({version: 1, scope, grant: input});
    for (const value of [...Object.values(scope), ...Object.values(input)]) expect(bytes.includes(Buffer.from(value))).toBe(false);
    const restarted = f.create(f);
    expect(await restarted.consumed(scope, input.requestId)).toBe(true);
    expect(await restarted.consume(scope, input)).toEqual({created: false});
    expect(await readFile(await oneFile(f.directory))).toEqual(bytes);
  });
  it.each(['claimId', 'contextSha256', 'deviceId'] as const)('rejects changed %s without replacing the original bytes', async field => {
    const f = await setup(); const input = grant(); await f.journal.consume(scope, input);
    const filename = await oneFile(f.directory); const bytes = await readFile(filename);
    await expect(f.journal.consume(scope, {...input, [field]: field === 'contextSha256' ? 'b'.repeat(64) : randomUUID()})).rejects.toThrow(/^OUTREACH_CONSUMPTION_CONFLICT$/);
    expect(await readFile(filename)).toEqual(bytes); expect(await f.journal.consumed(scope, input.requestId)).toBe(true);
  });
  it('isolates tenant, user, origin and request while snapshotting inputs before awaits', async () => {
    const f = await setup(); const input = grant(); const suppliedScope = {...scope}; const suppliedGrant = {...input};
    const pending = f.journal.consume(suppliedScope, suppliedGrant); suppliedScope.tenantId = 'changed'; suppliedGrant.claimId = randomUUID();
    expect(await pending).toEqual({created: true}); expect(await f.journal.consume(scope, input)).toEqual({created: false});
    for (const alternate of [{...scope, tenantId: 'other'}, {...scope, userId: 'other'}, {...scope, serviceOrigin: 'https://other.example'}]) {
      expect(await f.journal.consumed(alternate, input.requestId)).toBe(false);
      expect(await f.journal.consume(alternate, input)).toEqual({created: true});
    }
    expect(await f.journal.consume(scope, {...input, requestId: randomUUID()})).toEqual({created: true});
    expect(await readdir(f.directory)).toHaveLength(5);
  });
  it('serializes calls across factories and permits exactly one immutable winner', async () => {
    const f = await setup(); const input = grant(); const other = f.create({...f, directory: path.join(f.directory, '.')});
    const results = await Promise.all(Array.from({length: 16}, (_, index) => (index % 2 ? other : f.journal).consume(scope, input)));
    expect(results.filter(result => result.created)).toHaveLength(1); await oneFile(f.directory);
  });
  it('uses exclusive file creation across independent Node processes', async () => {
    const f = await setup(); const input = grant(); const secret = randomBytes(32);
    const script = `import {createCipheriv, createDecipheriv, randomBytes} from 'node:crypto';
      import {createOutreachConsumptionJournal} from ${JSON.stringify(pathToFileURL(modulePath).href)};
      const secret = Buffer.from(${JSON.stringify(secret.toString('hex'))}, 'hex');
      const protection = {
        isEncryptionAvailable: () => true,
        encryptString(plain) {
          const iv = randomBytes(12); const cipher = createCipheriv('aes-256-gcm', secret, iv);
          return Buffer.concat([iv, cipher.update(plain, 'utf8'), cipher.final(), cipher.getAuthTag()]);
        },
        decryptString(bytes) {
          const cipher = createDecipheriv('aes-256-gcm', secret, bytes.subarray(0, 12)); cipher.setAuthTag(bytes.subarray(-16));
          return Buffer.concat([cipher.update(bytes.subarray(12, -16)), cipher.final()]).toString('utf8');
        }
      };
      const journal = createOutreachConsumptionJournal({directory:${JSON.stringify(f.directory)}, protection});
      process.stdout.write('READY\\n');
      process.stdin.once('data', async () => {
        try {process.stdout.write(JSON.stringify(await journal.consume(${JSON.stringify(scope)}, ${JSON.stringify(input)})));}
        catch(error) {process.stdout.write(JSON.stringify({error:error.message}));}
        process.stdin.pause();
      });`;
    const processes = Array.from({length: 4}, () => {
      const child = spawn(process.execPath, ['--input-type=module', '--eval', script], {stdio: ['pipe', 'pipe', 'pipe']});
      let output = ''; let errors = ''; let ready!: () => void;
      const prepared = new Promise<void>(resolve => {ready = resolve;});
      const completed = new Promise<{created?: boolean; error?: string}>((resolve, reject) => {
        child.stdout.on('data', data => {output += data; if (output.includes('READY\n')) ready();});
        child.stderr.on('data', data => {errors += data;}); child.on('error', reject);
        child.on('close', code => {ready(); if (code !== 0) reject(new Error(errors)); else {try {resolve(JSON.parse(output.split('READY\n')[1]));} catch (error) {reject(error);}}});
      });
      return {child, prepared, completed};
    });
    await Promise.all(processes.map(item => item.prepared)); processes.forEach(item => item.child.stdin.end('go'));
    const results = await Promise.all(processes.map(item => item.completed));
    expect(results.filter(result => result.created === true), JSON.stringify(results)).toHaveLength(1);
    for (const result of results) expect(result.created === false || result.created === true || /^OUTREACH_CONSUMPTION_(INVALID_RECORD|PROTECTION_FAILED|STORAGE_FAILED)$/.test(result.error ?? '')).toBe(true);
    expect(await f.create({...f, protection: protection(secret)}).consumed(scope, input.requestId)).toBe(true);
  });
  it.each(['empty', 'oversized', 'ciphertext', 'scope', 'requestId', 'extra'])('preserves corrupt %s and rejects both APIs', async mode => {
    const f = await setup(); const input = grant(); await f.journal.consume(scope, input);
    const filename = await oneFile(f.directory); const record: any = {version: 1, scope: {...scope}, grant: {...input}};
    if (mode === 'scope') record.scope.tenantId = 'wrong'; if (mode === 'requestId') record.grant.requestId = randomUUID();
    if (mode === 'extra') record.message = 'not permitted';
    const bytes = mode === 'empty' ? Buffer.alloc(0) : mode === 'oversized' ? Buffer.alloc(65_537) : mode === 'ciphertext' ? Buffer.from('corrupt') : f.protection.encryptString(JSON.stringify(record));
    await writeFile(filename, bytes);
    await expect(f.journal.consume(scope, input)).rejects.toThrow(/^OUTREACH_CONSUMPTION_(INVALID_RECORD|PROTECTION_FAILED)$/);
    await expect(f.journal.consumed(scope, input.requestId)).rejects.toThrow(/^OUTREACH_CONSUMPTION_(INVALID_RECORD|PROTECTION_FAILED)$/);
    expect(await readFile(filename)).toEqual(bytes);
  });
  it('preserves partial writes and cannot turn them into fresh sending permission', async () => {
    const f = await setup(); const input = grant(); faults.partialWrite = true;
    await expect(f.journal.consume(scope, input)).rejects.toThrow(/^OUTREACH_CONSUMPTION_STORAGE_FAILED$/);
    const filename = await oneFile(f.directory); expect(await readFile(filename)).toHaveLength(10);
    await expect(f.create(f).consume(scope, input)).rejects.toThrow(/^OUTREACH_CONSUMPTION_PROTECTION_FAILED$/);
    await expect(f.journal.consumed(scope, input.requestId)).rejects.toThrow(/^OUTREACH_CONSUMPTION_PROTECTION_FAILED$/);
    expect(await readFile(filename)).toHaveLength(10);
  });
  it('does not grant permission on sync failure, even when full ciphertext remains', async () => {
    const f = await setup(); const input = grant(); faults.failSync = true;
    await expect(f.journal.consume(scope, input)).rejects.toThrow(/^OUTREACH_CONSUMPTION_STORAGE_FAILED$/);
    faults.failSync = false;
    expect(await f.create(f).consume(scope, input)).toEqual({created: false});
    expect(await f.journal.consumed(scope, input.requestId)).toBe(true);
  });
  it('rejects unavailable protection, encryption failure and unwritable storage with fixed errors', async () => {
    const f = await setup(); const input = grant(); const available = vi.spyOn(f.protection, 'isEncryptionAvailable').mockReturnValue(false);
    await expect(f.journal.consume(scope, input)).rejects.toThrow(/^OUTREACH_CONSUMPTION_PROTECTION_UNAVAILABLE$/);
    await expect(f.journal.consumed(scope, input.requestId)).rejects.toThrow(/^OUTREACH_CONSUMPTION_PROTECTION_UNAVAILABLE$/);
    expect(await readdir(f.root)).toEqual([]); available.mockRestore();
    const encrypt = vi.spyOn(f.protection, 'encryptString').mockImplementation(() => {throw new Error('/private/secret');});
    await expect(f.journal.consume(scope, input)).rejects.toThrow(/^OUTREACH_CONSUMPTION_PROTECTION_FAILED$/);
    expect(await readdir(f.directory)).toEqual([]); encrypt.mockRestore(); faults.denyCreate = true;
    await expect(f.journal.consume(scope, input)).rejects.toThrow(/^OUTREACH_CONSUMPTION_STORAGE_FAILED$/);
    expect(await readdir(f.directory)).toEqual([]);
  });
  it('rejects record symlinks without changing the target', async context => {
    const f = await setup(); const input = grant(); await f.journal.consume(scope, input);
    const filename = await oneFile(f.directory); const bytes = await readFile(filename); const target = path.join(f.root, 'target');
    await writeFile(target, bytes); await rm(filename);
    try {await symlink(target, filename, 'file');} catch (error) {
      if (process.platform === 'win32' && (error as NodeJS.ErrnoException).code === 'EPERM') {
        context.skip('Windows file symlink privilege unavailable; directory junction coverage runs separately');
        return;
      }
      throw error;
    }
    await expect(f.journal.consume(scope, input)).rejects.toThrow(/^OUTREACH_CONSUMPTION_INVALID_RECORD$/);
    await expect(f.journal.consumed(scope, input.requestId)).rejects.toThrow(/^OUTREACH_CONSUMPTION_INVALID_RECORD$/);
    expect(await readFile(target)).toEqual(bytes);
  });
  it('rejects non-files and never writes through a directory symlink', async () => {
    const f = await setup(); const input = grant(); await f.journal.consume(scope, input);
    const filename = await oneFile(f.directory); const bytes = await readFile(filename);
    const target = path.join(f.root, 'target'); await writeFile(target, bytes);
    await rm(filename); await mkdir(filename);
    await expect(f.journal.consume(scope, input)).rejects.toThrow(/^OUTREACH_CONSUMPTION_INVALID_RECORD$/);
    await expect(f.journal.consumed(scope, input.requestId)).rejects.toThrow(/^OUTREACH_CONSUMPTION_INVALID_RECORD$/);
    const linked = path.join(f.root, 'linked'); await symlink(f.directory, linked, process.platform === 'win32' ? 'junction' : 'dir');
    await expect(f.create({...f, directory: linked}).consume(scope, grant())).rejects.toThrow(/^OUTREACH_CONSUMPTION_STORAGE_FAILED$/);
    await expect(f.create({...f, directory: target}).consumed(scope, input.requestId)).rejects.toThrow(/^OUTREACH_CONSUMPTION_STORAGE_FAILED$/);
    expect(await readdir(f.directory)).toEqual([path.basename(filename)]);
    expect(await readFile(target)).toEqual(bytes);
  });
  it('rejects malformed identifiers, extra fields and unsafe directory before storage', async () => {
    const f = await setup(); const input = grant();
    for (const value of [{...scope, tenantId: ''}, {...scope, session: 'secret'}, {...scope, serviceOrigin: 'http://public.example'}, {...scope, userId: '\ud800'}]) {
      await expect(f.journal.consume(value, input)).rejects.toThrow(/^OUTREACH_CONSUMPTION_INVALID_SCOPE$/);
    }
    for (const value of [{...input, claimId: '../secret'}, {...input, message: 'secret'}, {...input, contextSha256: 'invalid'}]) {
      await expect(f.journal.consume(scope, value)).rejects.toThrow(/^OUTREACH_CONSUMPTION_INVALID_RECORD$/);
    }
    await expect(f.journal.consumed(scope, '../secret')).rejects.toThrow(/^OUTREACH_CONSUMPTION_INVALID_RECORD$/);
    for (const directory of ['relative', path.parse(f.root).root]) expect(() => f.create({...f, directory})).toThrow(/^OUTREACH_CONSUMPTION_STORAGE_FAILED$/);
    expect(await readdir(f.root)).toEqual([]);
  });
});
