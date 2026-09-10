import {expect, it} from 'vitest';
import {createCipheriv, createDecipheriv, createHash, randomBytes, randomUUID} from 'node:crypto';
import {mkdtemp, rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {configuredService, createServiceClient} from '../../src/main/serviceClient';
import {createDeviceKeyVault, type DeviceKeyProtection} from '../../src/main/deviceKeyVault';
import {createDeviceIdentityJournal} from '../../src/main/deviceIdentityJournal';
import {createDeviceIdentitySession} from '../../src/main/deviceIdentitySession';

const names = ['BASE', 'USER', 'TOKEN', 'NEXT_TOKEN', 'PEER_TOKEN'] as const;
const enabled = names.some(name => Boolean(process.env[`YIKE_DEVICE_LIVE_${name}`]));

// Only the Python parent starts this test with disposable authenticated HTTP/PG.
// The protection adapter is synthetic; Windows safeStorage is verified separately.
it.skipIf(!enabled)('recovers persisted device requests over actual HTTP and restricted PostgreSQL', async () => {
  const values = Object.fromEntries(names.map(name => [name, process.env[`YIKE_DEVICE_LIVE_${name}`]]));
  expect(Object.values(values).every(Boolean)).toBe(true);
  expect(Object.keys(process.env).filter(name => /DATABASE|^POSTGRES_/i.test(name))).toEqual([]);
  expect(process.versions.node.split('.')[0]).toBe('24');
  const base = values.BASE!;
  expect(new URL(base).hostname).toBe('127.0.0.1');
  expect(configuredService(base, {packaged: false, allowLoopbackHttp: true})).toBe(base);
  const root = await mkdtemp(path.join(os.tmpdir(), 'yike-device-http-'));
  const secret = randomBytes(32);
  const protection: DeviceKeyProtection = {
    isEncryptionAvailable: () => true,
    encryptString(value) {
      const iv = randomBytes(12);
      const cipher = createCipheriv('aes-256-gcm', secret, iv);
      return Buffer.concat([iv, cipher.update(value, 'utf8'), cipher.final(), cipher.getAuthTag()]);
    },
    decryptString(value) {
      const decipher = createDecipheriv('aes-256-gcm', secret, value.subarray(0, 12));
      decipher.setAuthTag(value.subarray(-16));
      return Buffer.concat([decipher.update(value.subarray(12, -16)), decipher.final()]).toString('utf8');
    },
  };
  let cookie = '';
  let loseRegistration = true;
  let loseCompletion = true;
  const calls: {method: string; path: string; requestId?: string; operation?: string}[] = [];
  const client = createServiceClient({baseUrl: base, clearSession: async () => {cookie = '';},
    fetch: async (url, options) => {
      expect(new URL(url).origin).toBe(base);
      const pathname = new URL(url).pathname;
      const body = typeof options.body === 'string' ? JSON.parse(options.body) : {};
      calls.push({method: options.method!, path: pathname, requestId: body.request_id, operation: body.operation});
      const headers = new Headers(options.headers);
      if (cookie) headers.set('Cookie', cookie);
      const response = await fetch(url, {...options, headers});
      const sessionCookie = response.headers.getSetCookie().find(value => value.startsWith('pilot_session='));
      if (sessionCookie) cookie = sessionCookie.split(';', 1)[0];
      expect(response.headers.get('cache-control')).toBe('no-store');
      if (response.ok && options.method === 'POST' &&
          ((loseRegistration && pathname.endsWith('/device-registrations')) ||
           (loseCompletion && pathname.endsWith('/complete')))) {
        if (pathname.endsWith('/device-registrations')) loseRegistration = false;
        else loseCompletion = false;
        await response.arrayBuffer(); // Real commit completed; only its network receipt is discarded.
        throw new TypeError('synthetic lost response');
      }
      return response;
    },
  });
  const scope = {serviceOrigin: base, userId: values.USER!};
  const journalOptions = {directory: path.join(root, 'identity'), protection};
  const vaultOptions = {directory: path.join(root, 'keys'), protection};
  const newCoordinator = () => createDeviceIdentitySession({serviceOrigin: base, deviceLabel: '合成 Windows 客户端',
    transport: client, journal: createDeviceIdentityJournal(journalOptions), vault: createDeviceKeyVault(vaultOptions)});
  let epoch = randomUUID();
  const context = () => {
    const snapshot = epoch;
    return {userId: values.USER!, sessionId: snapshot, isCurrent: () => epoch === snapshot};
  };
  try {
    expect(await client.request({operation: 'session.login', payload: {token: values.TOKEN}})).toMatchObject({ok: true});
    let coordinator = newCoordinator();
    const firstSession = context();
    expect((await coordinator.prepare(firstSession)).state).toBe('REGISTRATION_UNKNOWN');
    const original = await createDeviceIdentityJournal(journalOptions).read(scope);
    expect(original).not.toBeNull();
    expect(original!.proof).toBeNull();

    // Reconstruct real disk-backed factories; recover original registration, then lose BIND receipt.
    coordinator = newCoordinator();
    expect((await coordinator.prepare(firstSession)).state).toBe('PROOF_UNKNOWN');
    const boundRequest = (await createDeviceIdentityJournal(journalOptions).read(scope))!;
    expect(boundRequest.registration).toEqual(original!.registration);
    expect(boundRequest.proof!.request.operation).toBe('BIND');
    const beforeRecovery = calls.length;
    const ready = await newCoordinator().prepare(firstSession);
    expect(ready).toMatchObject({state: 'READY', credentialVersion: 1});
    if (ready.state !== 'READY') throw new Error('device must be ready after original receipt recovery');
    expect(calls.slice(beforeRecovery).every(call => call.method === 'GET')).toBe(true);
    const key = await createDeviceKeyVault(vaultOptions).read({...scope, deviceId: ready.deviceId});
    expect(key).not.toBeNull();

    // Different authenticated server session AND local epoch: historical BIND is not current proof.
    epoch = randomUUID();
    expect(await client.request({operation: 'session.logout'})).toMatchObject({ok: true});
    expect(await client.request({operation: 'session.login', payload: {token: values.NEXT_TOKEN}})).toMatchObject({ok: true});
    const secondSession = context();
    const again = await newCoordinator().prepare(secondSession);
    expect(again).toEqual(ready);
    const proved = (await createDeviceIdentityJournal(journalOptions).read(scope))!;
    expect(proved.proof!.request.operation).toBe('PROVE');
    expect(proved.proof!.sessionId).toBe(secondSession.sessionId);
    expect(proved.proof!.request.request_id).not.toBe(boundRequest.proof!.request.request_id);
    const reread = await createDeviceKeyVault(vaultOptions).read({...scope, deviceId: ready.deviceId});
    expect(reread?.publicKey).toBe(key!.publicKey);
    expect(calls.filter(call => call.method === 'POST' && call.path.endsWith('/device-registrations'))).toHaveLength(1);
    expect(calls.filter(call => call.operation === 'BIND')).toHaveLength(1);
    expect(calls.filter(call => call.operation === 'PROVE')).toHaveLength(1);
    expect(calls.filter(call => call.method === 'POST' && call.path.endsWith('/complete'))).toHaveLength(2);

    // Existing backend revocation is test-only setup, not a new public/private client operation.
    const revoked = await fetch(`${base}/api/ui/devices/${ready.deviceId}/revoke`, {
      method: 'POST', headers: {Origin: base, Cookie: cookie}, redirect: 'manual',
    });
    expect(revoked.status).toBe(200);
    const beforeRevokeRead = calls.length;
    expect((await newCoordinator().prepare(secondSession)).state).toBe('REVOKED');
    expect(calls.slice(beforeRevokeRead).every(call => call.method === 'GET')).toBe(true);
    expect(await client.request({operation: 'session.login', payload: {token: values.PEER_TOKEN}})).toMatchObject({ok: true});
    expect(await client.requestDevice({operation: 'devices.identity', payload: {device_id: ready.deviceId}}))
      .toMatchObject({ok: false, status: 404});
    epoch = randomUUID();
    expect(await client.request({operation: 'session.logout'})).toMatchObject({ok: true});
    expect(await client.requestDevice({operation: 'devices.identity', payload: {device_id: ready.deviceId}}))
      .toMatchObject({ok: false, status: 401});
    const afterLogout = calls.length;
    expect((await coordinator.prepare(secondSession)).state).toBe('SESSION_CHANGED');
    expect(calls).toHaveLength(afterLogout);
    console.log('DEVICE_LIVE_RESULT:' + JSON.stringify({deviceId: ready.deviceId,
      registrationId: original!.registration.request_id,
      bindRequestId: boundRequest.proof!.request.request_id, proveRequestId: proved.proof!.request.request_id,
      publicKeyHash: createHash('sha256').update(key!.publicKey).digest('hex')}));
  } finally {
    if (path.dirname(root) !== path.resolve(os.tmpdir()) || !path.basename(root).startsWith('yike-device-http-')) {
      throw new Error('UNSAFE_DEVICE_TEST_CLEANUP');
    }
    await rm(root, {recursive: true, force: true});
  }
});
