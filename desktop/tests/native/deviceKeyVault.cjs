// Explicit native fixture; never imported by the application or Vitest.
const {app, safeStorage} = require('electron');
const {createHash, createPublicKey, randomBytes, verify} = require('node:crypto');
const {mkdirSync, readFileSync, readdirSync} = require('node:fs');
const path = require('node:path');
const os = require('node:os');

const root = path.resolve(process.argv[2] || '');
const runIndex = process.argv[3];
if (process.platform !== 'win32' || path.dirname(root) !== path.resolve(os.tmpdir()) ||
    !path.basename(root).startsWith('yike-native-device-vault-') || !['0', '1'].includes(runIndex)) {
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
    const {createDeviceIdentityJournal} = require(path.join(root, 'journal.cjs'));
    if (!safeStorage.isEncryptionAvailable()) throw new Error('NATIVE_PROTECTION_UNAVAILABLE');
    const encrypted = safeStorage.encryptString('isolated native fixture');
    if (safeStorage.decryptString(encrypted) !== 'isolated native fixture') throw new Error('NATIVE_ROUNDTRIP_FAILED');
    const directory = path.join(profile, 'device-keys');
    const options = {directory, protection: safeStorage};
    const scope = {serviceOrigin: 'https://native-test.example', userId: '隔离原生测试', deviceId: '12345678-1234-4234-8234-123456789abc'};
    const key = await createDeviceKeyVault(options).getOrCreate(scope);
    const reopened = await createDeviceKeyVault(options).read(scope);
    if (!reopened || key.publicKey !== reopened.publicKey) throw new Error('NATIVE_REOPEN_FAILED');
    if (await createDeviceKeyVault(options).read({...scope, deviceId: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'}) !== null) {
      throw new Error('NATIVE_READ_CREATED_KEY');
    }
    const now = Math.floor(Date.now() / 1000);
    const request = {request_id: '22222222-2222-4222-8222-222222222222', operation: 'BIND', expected_credential_version: 0, public_key: key.publicKey};
    const journalDirectory = path.join(profile, 'device-identity');
    const journalOptions = {directory: journalDirectory, protection: safeStorage};
    const journalScope = {serviceOrigin: scope.serviceOrigin, userId: scope.userId};
    const journal = createDeviceIdentityJournal(journalOptions);
    const prior = await journal.read(journalScope);
    if ((runIndex === '0') !== (prior === null)) throw new Error('NATIVE_JOURNAL_RESTART_STATE');
    const loaded = await journal.loadOrCreate(journalScope, runIndex === '0' ? '原生隔离设备' : '新标签不得改原登记');
    if (loaded.created !== (runIndex === '0') || loaded.record.registration.device_label !== '原生隔离设备') {
      throw new Error('NATIVE_JOURNAL_REGISTRATION_CHANGED');
    }
    if (runIndex === '0') {
      await journal.setProof(journalScope, loaded.record.registration.request_id, null, {
        deviceId: scope.deviceId, sessionId: '44444444-4444-4444-4444-444444444444', request
      });
    }
    const journalRecord = await createDeviceIdentityJournal(journalOptions).read(journalScope);
    if (!journalRecord || journalRecord.proof?.request.request_id !== request.request_id ||
        journalRecord.proof.request.public_key !== key.publicKey) throw new Error('NATIVE_JOURNAL_PROOF_MISMATCH');
    const journalFiles = readdirSync(journalDirectory);
    if (journalFiles.length !== 1) throw new Error('NATIVE_JOURNAL_FILE_COUNT');
    const journalStored = readFileSync(path.join(journalDirectory, journalFiles[0]));
    if (journalStored.includes(Buffer.from(scope.userId)) || journalStored.includes(Buffer.from('原生隔离设备'))) {
      throw new Error('NATIVE_JOURNAL_PLAINTEXT');
    }
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
      readOnlyKey: true, journalPersisted: true,
      registrationId: journalRecord.registration.request_id,
      journalCiphertextSha256: createHash('sha256').update(journalStored).digest('hex'),
      publicKeySha256: createHash('sha256').update(key.publicKey).digest('hex'),
      ciphertextSha256: createHash('sha256').update(stored).digest('hex')
    }));
    app.exit(0);
  }).catch(() => {
    console.error('YIKE_NATIVE_DEVICE_VAULT_FAILED');
    app.exit(1);
  });
}
