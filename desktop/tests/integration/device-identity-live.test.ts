import {expect, it} from 'vitest';
import {createCipheriv, createDecipheriv, createHash, randomBytes} from 'node:crypto';
import {mkdtemp, rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {configuredService, createServiceClient} from '../../src/main/serviceClient';
import {createDeviceKeyVault, type DeviceKeyProtection} from '../../src/main/deviceKeyVault';
import {createDeviceIdentityJournal} from '../../src/main/deviceIdentityJournal';
import {createDeviceIdentitySession} from '../../src/main/deviceIdentitySession';
import {createDeviceIdentityController} from '../../src/main/deviceIdentityController';

const names = ['BASE', 'USER', 'TOKEN', 'NEXT_TOKEN', 'PEER_TOKEN'] as const;
const enabled = names.some(name => Boolean(process.env[`YIKE_DEVICE_LIVE_${name}`]));

// Only the Python parent starts this test with disposable authenticated HTTP/PG.
// The protection adapter is synthetic; Windows safeStorage is verified separately.
it.skipIf(!enabled)('recovers controller-owned device identity over actual HTTP and restricted PostgreSQL', async () => {
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
  let sessionReadGate: {entered(): void; released: Promise<void>} | null = null;
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
      // Hold one real authenticated response to test logout invalidation before it arrives.
      if (sessionReadGate && options.method === 'GET' && pathname === '/api/ui/session') {
        const gate = sessionReadGate;
        sessionReadGate = null;
        gate.entered();
        await gate.released;
      }
      return response;
    },
  });
  const scope = {serviceOrigin: base, userId: values.USER!};
  const journalOptions = {directory: path.join(root, 'identity'), protection};
  const vaultOptions = {directory: path.join(root, 'keys'), protection};
  let coordinatorCount = 0;
  const newController = () => createDeviceIdentityController({service: client, identityFactory: transport => {
    coordinatorCount++;
    // Reconstruct disk-backed factories without manufacturing a new authenticated epoch.
    return createDeviceIdentitySession({serviceOrigin: base, deviceLabel: '合成 Windows 客户端',
      transport, journal: createDeviceIdentityJournal(journalOptions), vault: createDeviceKeyVault(vaultOptions)});
  }});
  try {
    let controller = newController();
    expect(await controller.requestApi({operation: 'session.login', payload: {token: values.TOKEN}})).toMatchObject({ok: true});
    expect(await controller.requestApi({operation: 'session.get'}))
      .toMatchObject({ok: true, data: {authenticated: true, user_id: values.USER}});
    const beforeFirstPrepare = calls.length;
    expect((await controller.prepare()).state).toBe('REGISTRATION_UNKNOWN');
    expect(calls[beforeFirstPrepare]).toMatchObject({method: 'GET', path: '/api/ui/session'});
    const original = await createDeviceIdentityJournal(journalOptions).read(scope);
    expect(original).not.toBeNull();
    expect(original!.proof).toBeNull();

    // Reconstruct real disk-backed factories; recover original registration, then lose BIND receipt.
    expect((await controller.prepare()).state).toBe('PROOF_UNKNOWN');
    const boundRequest = (await createDeviceIdentityJournal(journalOptions).read(scope))!;
    expect(boundRequest.registration).toEqual(original!.registration);
    expect(boundRequest.proof!.request.operation).toBe('BIND');
    const beforeRecovery = calls.length;
    const ready = await controller.prepare();
    expect(ready).toMatchObject({state: 'READY', credentialVersion: 1});
    if (ready.state !== 'READY') throw new Error('device must be ready after original receipt recovery');
    expect(calls.slice(beforeRecovery).every(call => call.method === 'GET')).toBe(true);
    expect(coordinatorCount).toBe(3);
    expect((await createDeviceIdentityJournal(journalOptions).read(scope))!.proof!.sessionId)
      .toBe(boundRequest.proof!.sessionId);
    const key = await createDeviceKeyVault(vaultOptions).read({...scope, deviceId: ready.deviceId});
    expect(key).not.toBeNull();

    // A real logout/login plus new controller models a client restart, unlike factory reconstruction above.
    expect(await controller.requestApi({operation: 'session.logout'})).toMatchObject({ok: true});
    controller = newController();
    expect(await controller.requestApi({operation: 'session.login', payload: {token: values.NEXT_TOKEN}})).toMatchObject({ok: true});
    const again = await controller.prepare();
    expect(again).toEqual(ready);
    const proved = (await createDeviceIdentityJournal(journalOptions).read(scope))!;
    expect(proved.proof!.request.operation).toBe('PROVE');
    expect(proved.proof!.sessionId).not.toBe(boundRequest.proof!.sessionId);
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
    expect((await controller.prepare()).state).toBe('REVOKED');
    expect(calls.slice(beforeRevokeRead).every(call => call.method === 'GET')).toBe(true);
    expect(await controller.requestApi({operation: 'session.login', payload: {token: values.PEER_TOKEN}})).toMatchObject({ok: true});
    const peer = await controller.requestApi({operation: 'session.get'});
    expect(peer).toMatchObject({ok: true, data: {authenticated: true}});
    if (!peer.ok) throw new Error('peer session must authenticate');
    expect((peer.data as {user_id: string}).user_id).not.toBe(values.USER);
    expect(await client.requestDevice({operation: 'devices.identity', payload: {device_id: ready.deviceId}}))
      .toMatchObject({ok: false, status: 404});

    // Session identity comes only from the server; a logout queued behind a held GET invalidates it immediately.
    let entered!: () => void;
    let release!: () => void;
    const held = new Promise<void>(resolve => {entered = resolve;});
    sessionReadGate = {entered, released: new Promise<void>(resolve => {release = resolve;})};
    const beforeStalePrepare = calls.length;
    const beforeStaleCoordinator = coordinatorCount;
    const stalePrepare = controller.prepare();
    await held;
    const logout = controller.requestApi({operation: 'session.logout'});
    release();
    expect((await stalePrepare).state).toBe('SESSION_CHANGED');
    expect(await logout).toMatchObject({ok: true});
    expect(coordinatorCount).toBe(beforeStaleCoordinator);
    expect(calls.slice(beforeStalePrepare).map(call => `${call.method} ${call.path}`))
      .toEqual(['GET /api/ui/session', 'DELETE /api/ui/session']);
    expect(await client.requestDevice({operation: 'devices.identity', payload: {device_id: ready.deviceId}}))
      .toMatchObject({ok: false, status: 401});
    const afterLogout = calls.length;
    expect((await controller.prepare()).state).toBe('SIGNED_OUT');
    expect(calls.slice(afterLogout).map(call => `${call.method} ${call.path}`)).toEqual(['GET /api/ui/session']);
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
