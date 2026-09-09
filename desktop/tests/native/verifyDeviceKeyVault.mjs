// Run explicitly with Node on Windows; does not touch the product's userData.
import {createRequire} from 'node:module';
import {mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import os from 'node:os';
import {rolldown} from 'rolldown';

if (process.platform !== 'win32') throw new Error('WINDOWS_NATIVE_CHECK_REQUIRED');
const require = createRequire(import.meta.url);
const executable = require('electron');
const source = readFileSync(new URL('../../src/main/deviceKeyVault.ts', import.meta.url), 'utf8');
const signingSources = Object.fromEntries(['main/deviceProofSigner.ts', 'shared/deviceProof.ts'].map(name => [name,
  createHash('sha256').update(readFileSync(new URL(`../../src/${name}`, import.meta.url))).digest('hex')
]));
const root = mkdtempSync(path.join(os.tmpdir(), 'yike-native-device-vault-'));
const bundle = await rolldown({
  input: {
    vault: fileURLToPath(new URL('../../src/main/deviceKeyVault.ts', import.meta.url)),
    proof: fileURLToPath(new URL('../../src/main/deviceProofSigner.ts', import.meta.url))
  },
  platform: 'node', external: id => id.startsWith('node:')
});
try { await bundle.write({dir: root, entryFileNames: '[name].cjs', chunkFileNames: '[name]-[hash].cjs', format: 'cjs'}); }
finally { await bundle.close(); }
const inheritedSystemKeys = new Set([
  'systemroot', 'windir', 'comspec', 'path', 'pathext', 'temp', 'tmp',
  'userprofile', 'localappdata', 'appdata', 'homedrive', 'homepath', 'systemdrive'
]);
const environment = Object.fromEntries(Object.entries(process.env)
  .filter(([key]) => inheritedSystemKeys.has(key.toLowerCase())));
const runs = [];
for (let index = 0; index < 2; index++) {
  const child = spawnSync(executable, [fileURLToPath(new URL('deviceKeyVault.cjs', import.meta.url)), root], {
    env: environment, encoding: 'utf8', windowsHide: true, timeout: 30_000, maxBuffer: 256 * 1024
  });
  if (child.error || child.status !== 0) throw new Error('NATIVE_DEVICE_VAULT_PROCESS_FAILED');
  const result = child.stdout.split(/\r?\n/).find(line => line.startsWith('YIKE_NATIVE_RESULT='));
  if (!result) throw new Error('NATIVE_DEVICE_VAULT_RESULT_MISSING');
  const value = JSON.parse(result.slice('YIKE_NATIVE_RESULT='.length));
  if (value.platform !== 'win32' || value.electron !== require('electron/package.json').version ||
      ['available', 'osRoundtrip', 'reopened', 'realSignature'].some(field => value[field] !== true) ||
      !/^[a-f0-9]{64}$/.test(value.publicKeySha256 ?? '') || !/^[a-f0-9]{64}$/.test(value.ciphertextSha256 ?? '')) {
    throw new Error('NATIVE_DEVICE_VAULT_RESULT_INVALID');
  }
  runs.push(value);
}
if (runs[0].publicKeySha256 !== runs[1].publicKeySha256 || runs[0].ciphertextSha256 !== runs[1].ciphertextSha256) {
  throw new Error('NATIVE_DEVICE_VAULT_RESTART_CHANGED_KEY');
}
const report = {
  sourceSha256: createHash('sha256').update(source).digest('hex'),
  signingSources,
  root, runs, restartedProcessSameKey: true,
  boundary: 'Isolated Windows safeStorage and key persistence only; no product login, HTTP, platform or installer acceptance.'
};
writeFileSync(path.join(root, 'result.json'), JSON.stringify(report, null, 2), {flag: 'wx'});
console.log(JSON.stringify(report, null, 2));
