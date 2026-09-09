import {afterEach, describe, expect, it, vi} from 'vitest';
import {createCipheriv, createDecipheriv, createPublicKey, generateKeyPairSync, randomBytes, sign, verify} from 'node:crypto';
import {mkdtemp, readdir, readFile, writeFile, mkdir, rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createDeviceKeyVault, type DeviceKeyProtection, type DeviceKeyScope} from '../src/main/deviceKeyVault';

const fileFaults = vi.hoisted(() => ({syncFailures: 0, syncCalls: 0, partialWrite: false}));
vi.mock('node:fs/promises', async importOriginal => {
  const original = await importOriginal<typeof import('node:fs/promises')>();
  return {...original, open: async (...args: Parameters<typeof original.open>) => {
    const handle = await original.open(...args);
    const sync = handle.sync.bind(handle);
    const write = handle.writeFile.bind(handle);
    handle.sync = async () => {
      fileFaults.syncCalls++;
      if (fileFaults.syncFailures > 0) {fileFaults.syncFailures--; throw new Error('private OS path');}
      return sync();
    };
    handle.writeFile = async (data, options) => {
      if (fileFaults.partialWrite) {
        fileFaults.partialWrite = false;
        await write(Buffer.from(data as Uint8Array).subarray(0, 10));
        throw new Error('private partial write detail');
      }
      return write(data, options);
    };
    return handle;
  }};
});

const scope: DeviceKeyScope = {
  serviceOrigin: 'https://service.example', userId: '企业用户😀',
  deviceId: '12345678-1234-4234-8234-123456789abc'
};
const temporaryDirectories: string[] = [];

// In-memory test protection only, not evidence of Windows safeStorage support.
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
    }
  };
}

async function setup() {
  const root = await mkdtemp(path.join(os.tmpdir(), 'yike-device-vault-'));
  temporaryDirectories.push(root);
  const directory = path.join(root, 'device-keys');
  const protection = testProtection();
  const options = {directory, protection};
  return {root, ...options, vault: createDeviceKeyVault(options)};
}

async function keyFile(directory: string) {
  const files = await readdir(directory);
  expect(files).toHaveLength(1);
  expect(files[0]).toMatch(/^[0-9a-f]{64}\.key$/);
  return path.join(directory, files[0]);
}

afterEach(async () => {
  vi.restoreAllMocks();
  fileFaults.syncFailures = 0;
  fileFaults.syncCalls = 0;
  fileFaults.partialWrite = false;
  for (const directory of temporaryDirectories.splice(0)) {
    const target = path.resolve(directory);
    if (path.dirname(target) !== path.resolve(os.tmpdir()) || !path.basename(target).startsWith('yike-device-vault-')) {
      throw new Error('UNSAFE_TEST_CLEANUP_TARGET');
    }
    await rm(target, {recursive: true, force: true});
  }
});

describe('main-process device key vault', () => {
  it('persists an encrypted Ed25519 key and reads the same material in a new vault instance', async () => {
    const fixture = await setup();
    const key = await fixture.vault.getOrCreate(scope);
    const ciphertext = await readFile(await keyFile(fixture.directory));
    expect(ciphertext.includes(Buffer.from(key.privateKey))).toBe(false);
    expect(ciphertext.includes(Buffer.from(scope.userId))).toBe(false);
    expect(key.privateKey).toMatch(/^-----BEGIN PRIVATE KEY-----/);
    expect(key.publicKey).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(createPublicKey(key.privateKey).export({format: 'jwk'}).x).toBe(key.publicKey);
    const message = Buffer.from('device proof 原文字节');
    expect(verify(null, message, createPublicKey(key.privateKey), sign(null, message, key.privateKey))).toBe(true);
    const reopened = await createDeviceKeyVault(fixture).getOrCreate(scope);
    expect(reopened).toEqual(key);
    expect(Object.isFrozen(reopened)).toBe(true);
    expect(Object.isFrozen(reopened.scope)).toBe(true);
  });

  it('fails without OS protection before creating storage or asking for encryption', async () => {
    const fixture = await setup();
    const encrypt = vi.spyOn(fixture.protection, 'encryptString');
    vi.spyOn(fixture.protection, 'isEncryptionAvailable').mockReturnValue(false);
    await expect(fixture.vault.getOrCreate(scope)).rejects.toThrow('DEVICE_KEY_PROTECTION_UNAVAILABLE');
    expect(encrypt).not.toHaveBeenCalled();
    expect(await readdir(fixture.root)).toEqual([]);
  });

  it('does not expose protection errors or save a plaintext fallback', async () => {
    const fixture = await setup();
    vi.spyOn(fixture.protection, 'encryptString').mockImplementation(() => {throw new Error('private secret detail');});
    await expect(fixture.vault.getOrCreate(scope)).rejects.toThrow(/^DEVICE_KEY_PROTECTION_FAILED$/);
    expect(await readdir(fixture.directory)).toEqual([]);
  });

  it('uses one persisted key during concurrent calls across two vault instances', async () => {
    const fixture = await setup();
    const second = createDeviceKeyVault({...fixture, directory: path.join(fixture.directory, '.')});
    const keys = await Promise.all(Array.from({length: 16}, (_, index) =>
      (index % 2 ? fixture.vault : second).getOrCreate({...scope})));
    expect(new Set(keys.map(key => key.publicKey)).size).toBe(1);
    await keyFile(fixture.directory);
  });

  it('keeps services, users and devices in separate fixed files', async () => {
    const fixture = await setup();
    const keys = await Promise.all([
      scope,
      {...scope, serviceOrigin: 'https://other.example'},
      {...scope, userId: '另一企业'},
      {...scope, deviceId: '87654321-1234-4234-8234-123456789abc'}
    ].map(value => fixture.vault.getOrCreate(value)));
    expect(new Set(keys.map(key => key.publicKey)).size).toBe(4);
    expect(await readdir(fixture.directory)).toHaveLength(4);
  });

  it('captures the input scope before an asynchronous caller can change it', async () => {
    const fixture = await setup();
    const supplied = {...scope};
    const pending = fixture.vault.getOrCreate(supplied);
    supplied.userId = 'changed';
    expect((await pending).scope).toEqual(scope);
  });

  it.each([
    {...scope, serviceOrigin: 'https://service.example/'},
    {...scope, serviceOrigin: 'https://user:secret@service.example'},
    {...scope, serviceOrigin: 'https://service.example/path'},
    {...scope, serviceOrigin: 'http://public.example'},
    {...scope, userId: ' padded '},
    {...scope, userId: 'bad\nuser'},
    {...scope, userId: ''},
    {...scope, deviceId: '../escape'},
    {...scope, deviceId: scope.deviceId.toUpperCase()},
    {...scope, deviceId: scope.deviceId + '\n'},
    {...scope, path: 'C:/elsewhere'}
  ])('rejects invalid/noncanonical scope without filesystem writes: %j', async supplied => {
    const fixture = await setup();
    await expect(fixture.vault.getOrCreate(supplied)).rejects.toThrow(/^DEVICE_KEY_INVALID_SCOPE$/);
    expect(await readdir(fixture.root)).toEqual([]);
  });

  it('accepts only canonical loopback HTTP for the existing trusted development service', async () => {
    const fixture = await setup();
    const key = await fixture.vault.getOrCreate({...scope, serviceOrigin: 'http://127.0.0.1:18765'});
    expect(key.scope.serviceOrigin).toBe('http://127.0.0.1:18765');
  });

  it.each(['empty', 'oversized', 'undecryptable'])('preserves %s files and never silently replaces the key', async state => {
    const fixture = await setup();
    await fixture.vault.getOrCreate(scope);
    const filename = await keyFile(fixture.directory);
    const bytes = state === 'empty' ? Buffer.alloc(0) : state === 'oversized' ? Buffer.alloc(65_537, 42) : Buffer.from('untrusted');
    await writeFile(filename, bytes);
    await expect(fixture.vault.getOrCreate(scope)).rejects.toThrow(/^DEVICE_KEY_(INVALID_RECORD|PROTECTION_FAILED)$/);
    expect(await readFile(filename)).toEqual(bytes);
  });

  it.each(['service', 'user', 'device', 'version', 'publicKey', 'privateKey', 'extra'])('rejects a decrypted record with wrong %s without overwriting it', async mismatch => {
    const fixture = await setup();
    await fixture.vault.getOrCreate(scope);
    const filename = await keyFile(fixture.directory);
    const record = JSON.parse(fixture.protection.decryptString(await readFile(filename)));
    if (mismatch === 'service') record.scope.serviceOrigin = 'https://other.example';
    if (mismatch === 'user') record.scope.userId = 'other';
    if (mismatch === 'device') record.scope.deviceId = '87654321-1234-4234-8234-123456789abc';
    if (mismatch === 'version') record.version = 2;
    if (mismatch === 'publicKey') record.publicKey = generateKeyPairSync('ed25519').publicKey.export({format: 'jwk'}).x;
    if (mismatch === 'privateKey') record.privateKey = generateKeyPairSync('ec', {namedCurve: 'prime256v1'}).privateKey.export({format: 'pem', type: 'pkcs8'});
    if (mismatch === 'extra') record.path = '/other';
    const bytes = fixture.protection.encryptString(JSON.stringify(record));
    await writeFile(filename, bytes);
    await expect(fixture.vault.getOrCreate(scope)).rejects.toThrow(/^DEVICE_KEY_INVALID_RECORD$/);
    expect(await readFile(filename)).toEqual(bytes);
  });

  it('fails closed on a non-directory storage path without touching the existing file', async () => {
    const fixture = await setup();
    await writeFile(fixture.directory, 'preserve existing');
    await expect(fixture.vault.getOrCreate(scope)).rejects.toThrow(/^DEVICE_KEY_STORAGE_FAILED$/);
    expect(await readFile(fixture.directory, 'utf8')).toBe('preserve existing');
  });

  it('does not recover an unreadable record by generating a new key', async () => {
    const fixture = await setup();
    await fixture.vault.getOrCreate(scope);
    const filename = await keyFile(fixture.directory);
    // A directory at the fixed filename is a real cross-platform read failure.
    await rm(filename);
    await mkdir(filename);
    await expect(fixture.vault.getOrCreate(scope)).rejects.toThrow(/^DEVICE_KEY_INVALID_RECORD$/);
    expect(await readdir(filename)).toEqual([]);
  });

  it('keeps a partial failed write and refuses to silently replace it', async () => {
    const fixture = await setup();
    fileFaults.partialWrite = true;
    await expect(fixture.vault.getOrCreate(scope)).rejects.toThrow(/^DEVICE_KEY_STORAGE_FAILED$/);
    const filename = await keyFile(fixture.directory);
    const partial = await readFile(filename);
    expect(partial).toHaveLength(10);
    await expect(fixture.vault.getOrCreate(scope)).rejects.toThrow(/^DEVICE_KEY_PROTECTION_FAILED$/);
    expect(await readFile(filename)).toEqual(partial);
  });

  it('does not treat a complete but failed-sync write as durable on retry', async () => {
    const fixture = await setup();
    fileFaults.syncFailures = 1;
    await expect(fixture.vault.getOrCreate(scope)).rejects.toThrow(/^DEVICE_KEY_STORAGE_FAILED$/);
    const filename = await keyFile(fixture.directory);
    const before = await readFile(filename);
    const callsBeforeRetry = fileFaults.syncCalls;
    await fixture.vault.getOrCreate(scope);
    expect(fileFaults.syncCalls).toBeGreaterThan(callsBeforeRetry);
    expect(await readFile(filename)).toEqual(before);
  });

  it('continues to refuse a stored key while flush errors persist', async () => {
    const fixture = await setup();
    fileFaults.syncFailures = 2;
    await expect(fixture.vault.getOrCreate(scope)).rejects.toThrow(/^DEVICE_KEY_STORAGE_FAILED$/);
    const filename = await keyFile(fixture.directory);
    const before = await readFile(filename);
    await expect(createDeviceKeyVault(fixture).getOrCreate(scope)).rejects.toThrow(/^DEVICE_KEY_STORAGE_FAILED$/);
    expect(fileFaults.syncCalls).toBe(2);
    expect(await readFile(filename)).toEqual(before);
    const key = await fixture.vault.getOrCreate(scope);
    expect(key.publicKey).toBe(JSON.parse(fixture.protection.decryptString(before)).publicKey);
  });
});
