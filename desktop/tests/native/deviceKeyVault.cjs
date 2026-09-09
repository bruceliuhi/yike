// Explicit native fixture; never imported by the application or Vitest.
const {app, safeStorage} = require('electron');
const {createHash, createPublicKey, randomBytes, verify} = require('node:crypto');
const {mkdirSync, readFileSync, readdirSync} = require('node:fs');
const path = require('node:path');
const os = require('node:os');

const root = path.resolve(process.argv[2] || '');
if (process.platform !== 'win32' || path.dirname(root) !== path.resolve(os.tmpdir()) ||
    !path.basename(root).startsWith('yike-native-device-vault-')) {
  app.exit(1);
} else {
  const profile = path.join(root, 'electron-profile');
  mkdirSync(profile, {recursive: true});
  app.setPath('userData', profile);
  app.setPath('sessionData', profile);
  app.setAppLogsPath(path.join(profile, 'logs'));
  app.disableHardwareAcceleration();
  app.whenReady().then(async () => {
    const {createDeviceKeyVault} = require(path.join(root, 'vault.cjs'));
    const {signDeviceChallenge} = require(path.join(root, 'proof.cjs'));
    if (!safeStorage.isEncryptionAvailable()) throw new Error('NATIVE_PROTECTION_UNAVAILABLE');
    const encrypted = safeStorage.encryptString('isolated native fixture');
    if (safeStorage.decryptString(encrypted) !== 'isolated native fixture') throw new Error('NATIVE_ROUNDTRIP_FAILED');
    const directory = path.join(profile, 'device-keys');
    const options = {directory, protection: safeStorage};
    const scope = {serviceOrigin: 'https://native-test.example', userId: '隔离原生测试', deviceId: '12345678-1234-4234-8234-123456789abc'};
    const key = await createDeviceKeyVault(options).getOrCreate(scope);
    const reopened = await createDeviceKeyVault(options).getOrCreate(scope);
    if (key.publicKey !== reopened.publicKey) throw new Error('NATIVE_REOPEN_FAILED');
    const now = Math.floor(Date.now() / 1000);
    const request = {request_id: '22222222-2222-4222-8222-222222222222', operation: 'BIND', expected_credential_version: 0, public_key: key.publicKey};
    const payload = {
      protocol: 'yike-device-proof-v1', tenant_id: 'native-tenant', user_id: scope.userId,
      device_id: scope.deviceId, request_id: request.request_id,
      challenge_id: '33333333-3333-4333-8333-333333333333', session_digest: 'a'.repeat(64),
      operation: 'BIND', expected_credential_version: 0, target_public_key: key.publicKey,
      nonce: randomBytes(32).toString('base64url'), expires_at: now + 120
    };
    // Controlled server-format challenge; not a real HTTP registration/BIND claim.
    const raw = JSON.stringify(Object.fromEntries(Object.entries(payload).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)))
      .replace(/[\u007f-\uffff]/g, character => '\\u' + character.charCodeAt(0).toString(16).padStart(4, '0'));
    const proof = signDeviceChallenge({key, nowSeconds: now,
      expected: {...scope, publicKey: key.publicKey, request},
      challenge: {request_id: request.request_id, challenge_id: payload.challenge_id, expires_at: payload.expires_at, signing_payload: raw}
    });
    if (proof.previous_signature !== null || !verify(null, Buffer.from(raw, 'utf8'), createPublicKey(key.privateKey), Buffer.from(proof.signature, 'base64url'))) {
      throw new Error('NATIVE_SIGNATURE_FAILED');
    }
    const files = readdirSync(directory);
    if (files.length !== 1) throw new Error('NATIVE_STORAGE_COUNT_FAILED');
    const stored = readFileSync(path.join(directory, files[0]));
    if (stored.includes(Buffer.from(key.privateKey)) || stored.includes(Buffer.from(scope.userId))) throw new Error('NATIVE_PLAINTEXT_FOUND');
    console.log('YIKE_NATIVE_RESULT=' + JSON.stringify({
      platform: process.platform, electron: process.versions.electron,
      available: true, osRoundtrip: true, reopened: true, realSignature: true,
      publicKeySha256: createHash('sha256').update(key.publicKey).digest('hex'),
      ciphertextSha256: createHash('sha256').update(stored).digest('hex')
    }));
    app.exit(0);
  }).catch(() => {
    console.error('YIKE_NATIVE_DEVICE_VAULT_FAILED');
    app.exit(1);
  });
}
