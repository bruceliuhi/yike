import { afterEach, describe, expect, it, vi } from 'vitest';
import { createCipheriv, createDecipheriv, randomBytes, randomUUID } from 'node:crypto';
import { mkdtemp, readdir, readFile, writeFile, mkdir, rm, symlink } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createDeviceIdentityJournal, type DeviceIdentityProof, type DeviceIdentityScope } from '../src/main/deviceIdentityJournal';
import type { DeviceKeyProtection } from '../src/main/deviceKeyVault';

const faults = vi.hoisted(() => ({syncCalls: 0, failSyncAt: 0, partialWrite: false, rename: false}));
vi.mock('node:fs/promises', async importOriginal => {
  const original = await importOriginal<typeof import('node:fs/promises')>();
  return {...original,
    rename: async (...args: Parameters<typeof original.rename>) => {
      if (faults.rename) throw new Error('sensitive rename path');
      return original.rename(...args);
    },
    open: async (...args: Parameters<typeof original.open>) => {
      const handle = await original.open(...args);
      const sync = handle.sync.bind(handle);
      const write = handle.writeFile.bind(handle);
      handle.sync = async () => {
        faults.syncCalls++;
        if (faults.syncCalls === faults.failSyncAt) throw new Error('sensitive sync path');
        return sync();
      };
      handle.writeFile = async (data, options) => {
        if (faults.partialWrite) {
          faults.partialWrite = false;
          await write(Buffer.from(data as Uint8Array).subarray(0, 10));
          throw new Error('sensitive write path');
        }
        return write(data, options);
      };
      return handle;
    },
  };
});

const scope: DeviceIdentityScope = {serviceOrigin: 'https://service.example', userId: '企业用户😀'};
const roots: string[] = [];
const label = 'Windows设备机密标签';

function testProtection(): DeviceKeyProtection {
  const secret = randomBytes(32);
  return {
    isEncryptionAvailable: () => true,
    encryptString(value) {
      const iv = randomBytes(12);
      const cipher = createCipheriv('aes-256-gcm', secret, iv);
      return Buffer.concat([iv, cipher.update(value, 'utf8'), cipher.final(), cipher.getAuthTag()]);
    },
    decryptString(value) {
      const cipher = createDecipheriv('aes-256-gcm', secret, value.subarray(0, 12));
      cipher.setAuthTag(value.subarray(-16));
      return Buffer.concat([cipher.update(value.subarray(12, -16)), cipher.final()]).toString('utf8');
    },
  };
}

async function setup() {
  const root = await mkdtemp(path.join(os.tmpdir(), 'yike-identity-journal-'));
  roots.push(root);
  const options = {directory: path.join(root, 'journal'), protection: testProtection()};
  return {root, ...options, journal: createDeviceIdentityJournal(options)};
}

async function recordFile(directory: string) {
  const files = (await readdir(directory)).filter(file => file.endsWith('.identity'));
  expect(files).toHaveLength(1);
  expect(files[0]).toMatch(/^[0-9a-f]{64}\.identity$/);
  return path.join(directory, files[0]);
}

function proof(): DeviceIdentityProof {
  return {deviceId: randomUUID(), sessionId: randomUUID(), request: {
    request_id: randomUUID(), operation: 'BIND', expected_credential_version: 0, public_key: 'A'.repeat(43),
  }};
}

afterEach(async () => {
  vi.restoreAllMocks();
  Object.assign(faults, {syncCalls: 0, failSyncAt: 0, partialWrite: false, rename: false});
  for (const directory of roots.splice(0)) {
    const target = path.resolve(directory);
    if (path.dirname(target) !== path.resolve(os.tmpdir()) || !path.basename(target).startsWith('yike-identity-journal-')) {
      throw new Error('UNSAFE_TEST_CLEANUP_TARGET');
    }
    await rm(target, {recursive: true, force: true});
  }
});

describe('device identity journal', () => {
  it('reads missing scope without making directory or record', async () => {
    const fixture = await setup();
    expect(await fixture.journal.read(scope)).toBeNull();
    expect(await readdir(fixture.root)).toEqual([]);
  });

  it('persists an encrypted original registration and returns frozen strict copies after restart', async () => {
    const fixture = await setup();
    const first = await fixture.journal.loadOrCreate(scope, `\u001c\u0085 ${label} \u3000`);
    expect(first.created).toBe(true);
    expect(first.record.registration).toEqual({request_id: expect.stringMatching(/^[0-9a-f-]{36}$/), device_label: label});
    expect(first.record).toEqual({version: 1, scope, registration: first.record.registration, proof: null});
    const bytes = await readFile(await recordFile(fixture.directory));
    expect(bytes.includes(Buffer.from(label))).toBe(false);
    expect(bytes.includes(Buffer.from(scope.userId))).toBe(false);
    const restarted = createDeviceIdentityJournal(fixture);
    const later = await restarted.loadOrCreate(scope, 'different label');
    expect(later).toEqual({record: first.record, created: false});
    const read = await restarted.read(scope);
    expect(read).toEqual(first.record);
    expect(read).not.toBe(first.record);
    expect(Object.isFrozen(read)).toBe(true);
    expect(Object.isFrozen(read!.scope)).toBe(true);
    expect(Object.isFrozen(read!.registration)).toBe(true);
  });

  it('serializes 16 calls across factories into one persisted UUID and one creator', async () => {
    const fixture = await setup();
    const other = createDeviceIdentityJournal({...fixture, directory: path.join(fixture.directory, '.')});
    const results = await Promise.all(Array.from({length: 16}, (_, index) =>
      (index % 2 ? fixture.journal : other).loadOrCreate({...scope}, label)));
    expect(new Set(results.map(value => value.record.registration.request_id)).size).toBe(1);
    expect(results.filter(value => value.created)).toHaveLength(1);
    await recordFile(fixture.directory);
  });

  it('isolates service/user scopes and permits canonical loopback and 256 Unicode codepoints', async () => {
    const fixture = await setup();
    const scopes = [scope, {...scope, userId: '另一个'}, {...scope, serviceOrigin: 'https://other.example'},
      {...scope, serviceOrigin: 'http://127.0.0.1:18765', userId: '😀'.repeat(256)}];
    const results = await Promise.all(scopes.map(value => fixture.journal.loadOrCreate(value, '😀'.repeat(128))));
    expect(new Set(results.map(value => value.record.registration.request_id)).size).toBe(4);
    expect(await readdir(fixture.directory)).toHaveLength(4);
  });

  it('captures caller scope and proof before awaits and freezes returned proof', async () => {
    const fixture = await setup();
    const input = {...scope};
    const pending = fixture.journal.loadOrCreate(input, label);
    input.userId = 'changed';
    const first = await pending;
    expect(first.record.scope).toEqual(scope);
    const next = proof();
    const expected = structuredClone(next);
    const supplied = {...scope};
    const change = fixture.journal.setProof(supplied, first.record.registration.request_id, null, next);
    supplied.userId = 'changed';
    next.request.request_id = randomUUID();
    const updated = await change;
    expect(updated.proof).toEqual(expected);
    expect(Object.isFrozen(updated.proof)).toBe(true);
    expect(Object.isFrozen(updated.proof!.request)).toBe(true);
    const readScope = {...scope};
    const reading = fixture.journal.read(readScope);
    readScope.userId = 'changed';
    expect(await reading).toEqual(updated);
  });

  it.each([
    null, {}, {...scope, path: 'private'}, {...scope, serviceOrigin: 'https://service.example/'},
    {...scope, serviceOrigin: 'https://user:password@service.example'}, {...scope, serviceOrigin: 'http://public.example'},
    {...scope, serviceOrigin: 'https://service.example/path'}, {...scope, serviceOrigin: 'HTTPS://service.example'},
    {...scope, userId: ''}, {...scope, userId: ' padded '}, {...scope, userId: 'bad\nuser'},
    {...scope, userId: '\ud800'}, {...scope, userId: '😀'.repeat(257)}, {...scope, [Symbol('extra')]: true},
  ])('rejects strict invalid scope before storage %#', async supplied => {
    const fixture = await setup();
    await expect(fixture.journal.loadOrCreate(supplied as DeviceIdentityScope, label)).rejects.toThrow(/^DEVICE_IDENTITY_JOURNAL_INVALID_SCOPE$/);
    await expect(fixture.journal.read(supplied as DeviceIdentityScope)).rejects.toThrow(/^DEVICE_IDENTITY_JOURNAL_INVALID_SCOPE$/);
    expect(await readdir(fixture.root)).toEqual([]);
  });

  it.each(['', '\udfff', 'label\0', '😀'.repeat(129), ' '.repeat(4096) + 'x'])('rejects invalid label before storage %#', async supplied => {
    const fixture = await setup();
    await expect(fixture.journal.loadOrCreate(scope, supplied)).rejects.toThrow(/^DEVICE_IDENTITY_JOURNAL_INVALID_RECORD$/);
    expect(await readdir(fixture.root)).toEqual([]);
  });

  it('atomically updates proof with registration and prior-proof CAS', async () => {
    const fixture = await setup();
    const initial = await fixture.journal.loadOrCreate(scope, label);
    const id = initial.record.registration.request_id;
    const bind = proof();
    const bound = await fixture.journal.setProof(scope, id, null, bind);
    expect(bound).toEqual({...initial.record, proof: bind});
    const filename = await recordFile(fixture.directory);
    const bytes = await readFile(filename);
    await expect(fixture.journal.setProof(scope, randomUUID(), bind.request.request_id, proof())).rejects.toThrow(/^DEVICE_IDENTITY_JOURNAL_CONFLICT$/);
    await expect(fixture.journal.setProof(scope, id, null, proof())).rejects.toThrow(/^DEVICE_IDENTITY_JOURNAL_CONFLICT$/);
    expect(await readFile(filename)).toEqual(bytes);
    const prove = {...proof(), request: {...proof().request, operation: 'PROVE' as const, expected_credential_version: 1, public_key: null}};
    const results = await Promise.allSettled([
      fixture.journal.setProof(scope, id, bind.request.request_id, prove),
      createDeviceIdentityJournal(fixture).setProof(scope, id, bind.request.request_id, proof()),
    ]);
    expect(results.filter(value => value.status === 'fulfilled')).toHaveLength(1);
    const final = await fixture.journal.read(scope);
    expect(final!.proof).toEqual(prove);
    expect(await readdir(fixture.directory)).toHaveLength(1);
  });

  it('does not create storage for a missing CAS target', async () => {
    const fixture = await setup();
    await expect(fixture.journal.setProof(scope, randomUUID(), null, proof())).rejects.toThrow(/^DEVICE_IDENTITY_JOURNAL_CONFLICT$/);
    expect(await readdir(fixture.root)).toEqual([]);
  });

  it.each(['registration', 'expected', 'session', 'request', 'extra', 'secret'])('validates CAS inputs before awaiting: %s', async field => {
    const fixture = await setup();
    const supplied = proof();
    if (field === 'session') (supplied as {sessionId: string}).sessionId = 'raw-token';
    if (field === 'request') supplied.request.operation = 'ROTATE' as 'BIND';
    if (field === 'extra') Object.assign(supplied, {extra: 'private'});
    if (field === 'secret') Object.assign(supplied.request, {signature: 'secret'});
    await expect(fixture.journal.setProof(scope, field === 'registration' ? 'wrong' : randomUUID(),
      field === 'expected' ? 'wrong' : null, supplied)).rejects.toThrow(/^DEVICE_IDENTITY_JOURNAL_INVALID_RECORD$/);
    expect(await readdir(fixture.root)).toEqual([]);
  });

  it('fails protection unavailable without filesystem creation', async () => {
    const fixture = await setup();
    vi.spyOn(fixture.protection, 'isEncryptionAvailable').mockReturnValue(false);
    await expect(fixture.journal.read(scope)).rejects.toThrow(/^DEVICE_IDENTITY_JOURNAL_PROTECTION_UNAVAILABLE$/);
    await expect(fixture.journal.loadOrCreate(scope, label)).rejects.toThrow(/^DEVICE_IDENTITY_JOURNAL_PROTECTION_UNAVAILABLE$/);
    expect(await readdir(fixture.root)).toEqual([]);
  });

  it('maps encryption exceptions to fixed error without plaintext fallback', async () => {
    const fixture = await setup();
    vi.spyOn(fixture.protection, 'encryptString').mockImplementation(() => {throw new Error('private detail');});
    await expect(fixture.journal.loadOrCreate(scope, label)).rejects.toThrow(/^DEVICE_IDENTITY_JOURNAL_PROTECTION_FAILED$/);
    expect(await readdir(fixture.directory)).toEqual([]);
  });

  it.each(['empty', 'oversized', 'ciphertext', 'json', 'scope', 'extra', 'proof', 'label', 'secret', 'plainOversized'])('preserves invalid stored %s record', async state => {
    const fixture = await setup();
    const initial = await fixture.journal.loadOrCreate(scope, label);
    const filename = await recordFile(fixture.directory);
    const bad = structuredClone(initial.record) as unknown as Record<string, any>;
    if (state === 'scope') bad.scope.userId = 'other';
    if (state === 'extra') bad.extra = 'secret';
    if (state === 'proof') bad.proof = {...proof(), sessionId: 'token'};
    if (state === 'label') bad.registration.device_label = ` ${label} `;
    if (state === 'secret') bad.proof = {...proof(), signature: 'private'};
    const bytes = state === 'empty' ? Buffer.alloc(0) : state === 'oversized' ? Buffer.alloc(65_537, 1)
      : state === 'ciphertext' ? Buffer.from('invalid') : fixture.protection.encryptString(state === 'json' ? '{'
        : state === 'plainOversized' ? ' '.repeat(65_537) : JSON.stringify(bad));
    await writeFile(filename, bytes);
    await expect(fixture.journal.loadOrCreate(scope, label)).rejects.toThrow(/^DEVICE_IDENTITY_JOURNAL_(INVALID_RECORD|PROTECTION_FAILED)$/);
    expect(await readFile(filename)).toEqual(bytes);
  });

  it('rejects a directory at the record path and a symlink journal directory', async () => {
    const fixture = await setup();
    await fixture.journal.loadOrCreate(scope, label);
    const filename = await recordFile(fixture.directory);
    await rm(filename);
    await mkdir(filename);
    await expect(fixture.journal.read(scope)).rejects.toThrow(/^DEVICE_IDENTITY_JOURNAL_INVALID_RECORD$/);
    const target = path.join(fixture.root, 'target');
    const link = path.join(fixture.root, 'linked');
    await mkdir(target);
    await symlink(target, link, process.platform === 'win32' ? 'junction' : 'dir');
    await expect(createDeviceIdentityJournal({...fixture, directory: link}).loadOrCreate(scope, label))
      .rejects.toThrow(/^DEVICE_IDENTITY_JOURNAL_STORAGE_FAILED$/);
    expect(await readdir(target)).toEqual([]);
  });

  it('preserves partial initial writes and never replaces them', async () => {
    const fixture = await setup();
    faults.partialWrite = true;
    await expect(fixture.journal.loadOrCreate(scope, label)).rejects.toThrow(/^DEVICE_IDENTITY_JOURNAL_STORAGE_FAILED$/);
    const filename = await recordFile(fixture.directory);
    expect(await readFile(filename)).toHaveLength(10);
    await expect(fixture.journal.loadOrCreate(scope, label)).rejects.toThrow(/^DEVICE_IDENTITY_JOURNAL_PROTECTION_FAILED$/);
    expect(await readFile(filename)).toHaveLength(10);
  });

  it('recovers complete failed-sync creation only after an existing read sync succeeds', async () => {
    const fixture = await setup();
    faults.failSyncAt = 1;
    await expect(fixture.journal.loadOrCreate(scope, label)).rejects.toThrow(/^DEVICE_IDENTITY_JOURNAL_STORAGE_FAILED$/);
    const filename = await recordFile(fixture.directory);
    const before = await readFile(filename);
    const original = JSON.parse(fixture.protection.decryptString(before));
    faults.failSyncAt = 2;
    await expect(createDeviceIdentityJournal(fixture).read(scope)).rejects.toThrow(/^DEVICE_IDENTITY_JOURNAL_STORAGE_FAILED$/);
    const recovered = await fixture.journal.loadOrCreate(scope, label);
    expect(recovered).toEqual({record: original, created: false});
    expect(await readFile(filename)).toEqual(before);
    expect(faults.syncCalls).toBe(3);
  });

  it.each(['write', 'sync', 'rename'])('preserves old target and failed temp on update %s failure', async stage => {
    const fixture = await setup();
    const initial = await fixture.journal.loadOrCreate(scope, label);
    const filename = await recordFile(fixture.directory);
    const before = await readFile(filename);
    faults.partialWrite = stage === 'write';
    faults.rename = stage === 'rename';
    if (stage === 'sync') faults.failSyncAt = faults.syncCalls + 2;
    await expect(fixture.journal.setProof(scope, initial.record.registration.request_id, null, proof()))
      .rejects.toThrow(/^DEVICE_IDENTITY_JOURNAL_STORAGE_FAILED$/);
    expect(await readFile(filename)).toEqual(before);
    expect((await readdir(fixture.directory)).filter(file => file.endsWith('.tmp'))).toHaveLength(1);
    expect(await fixture.journal.read(scope)).toEqual(initial.record);
  });

  it('does not report update success after rename if target sync fails, then recovers exact proof', async () => {
    const fixture = await setup();
    const initial = await fixture.journal.loadOrCreate(scope, label);
    const next = proof();
    faults.failSyncAt = faults.syncCalls + 3;
    await expect(fixture.journal.setProof(scope, initial.record.registration.request_id, null, next))
      .rejects.toThrow(/^DEVICE_IDENTITY_JOURNAL_STORAGE_FAILED$/);
    const read = await createDeviceIdentityJournal(fixture).read(scope);
    expect(read).toEqual({...initial.record, proof: next});
    expect(faults.syncCalls).toBe(5);
    expect(await readdir(fixture.directory)).toHaveLength(1);
  });

  it.each(['relative', path.parse(process.cwd()).root])('rejects unsafe directory %s', directory => {
    expect(() => createDeviceIdentityJournal({directory, protection: testProtection()}))
      .toThrow(/^DEVICE_IDENTITY_JOURNAL_STORAGE_FAILED$/);
  });
});
