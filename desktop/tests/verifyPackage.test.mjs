import {afterEach, describe, expect, it} from 'vitest';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {finished} from 'node:stream/promises';
import {mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import asar from '@electron/asar';

const script = fileURLToPath(new URL('../scripts/verify-package.mjs', import.meta.url));
const temporaryParent = realpathSync(os.tmpdir());
const roots = [];
const rendererRoot = '.vite/renderer/main_window/';
const manifestPath = rendererRoot + '.vite/manifest.json';
const pkg = {name: 'asar-verification-fixture', version: '0.2.0', main: '.vite/build/main.cjs'};
const manifest = {
  'index.html': {file: 'assets/main-abc.js', isEntry: true, css: ['assets/main-abc.css'], assets: ['assets/logo-abc.png']},
  'lazy.ts': {file: 'assets/lazy-def.js', isDynamicEntry: true},
};
const rendererBytes = {
  'index.html': '<html><body>真实 ASAR fixture</body></html>',
  'assets/main-abc.js': 'console.log("main renderer");\n',
  'assets/main-abc.css': 'body { color: blue; }\n',
  'assets/logo-abc.png': Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
  'assets/lazy-def.js': 'export const lazy = true;\n',
};
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const fileDigest = file => digest(readFileSync(file));

async function archiveFixture(overrides = {}) {
  const root = mkdtempSync(path.join(temporaryParent, 'yike asar verification '));
  roots.push(root);
  const source = path.join(root, '源 files');
  const files = {
    'package.json': JSON.stringify(pkg),
    [pkg.main]: 'exports.fixture = true;\n',
    '.vite/build/preload.cjs': 'console.log("preload fixture");\n',
    [manifestPath]: JSON.stringify(manifest),
    ...Object.fromEntries(Object.entries(rendererBytes).map(([name, bytes]) => [rendererRoot + name, bytes])),
    // Present but not allowlisted; the traversal counterexample must not fail merely because it is absent.
    [rendererRoot + 'escape.js']: 'not an allowlisted renderer asset\n',
    ...overrides,
  };
  for (const [name, bytes] of Object.entries(files)) {
    if (bytes === null) continue;
    const destination = path.join(source, ...name.split('/'));
    mkdirSync(path.dirname(destination), {recursive: true});
    writeFileSync(destination, bytes);
  }
  const archive = path.join(root, '真实 package.asar');
  // Locked asar 3.4.1 resolves with an ended WriteStream before its writes finish.
  // Let it flush before a synchronous child process reads the archive bytes.
  await finished(await asar.createPackage(source, archive));
  return archive;
}
function verify(archive) {
  const before = fileDigest(archive);
  const result = spawnSync(process.execPath, [script, archive], {
    cwd: path.dirname(archive), encoding: 'utf8', windowsHide: true, timeout: 15000,
  });
  expect(result.error).toBeUndefined();
  expect(fileDigest(archive)).toBe(before);
  return result;
}
async function rejects(overrides, expectedError) {
  const result = verify(await archiveFixture(overrides));
  expect(result.status, result.stdout + result.stderr).toBe(1);
  expect(result.stdout).toBe('');
  expect(result.stderr).toContain(expectedError);
}
afterEach(() => {
  for (const root of roots.splice(0)) {
    if (!path.isAbsolute(root) || path.dirname(root) !== temporaryParent ||
      !path.basename(root).startsWith('yike asar verification ') || realpathSync(root) !== root) {
      throw new Error('Unsafe ASAR fixture cleanup');
    }
    rmSync(root, {recursive: true, force: true});
  }
});

describe('packaged ASAR CLI verification', () => {
  it('verifies a complete real archive in a spaced Unicode path and reports exact allowlisted hashes', async () => {
    const archive = await archiveFixture();
    const result = verify(archive);
    expect(result.status, result.stderr).toBe(0);
    const report = JSON.parse(result.stdout);
    expect(report).toEqual({
      archive: path.resolve(archive), version: pkg.version, main: pkg.main,
      rendererAssetCount: Object.keys(rendererBytes).length, archiveSha256: fileDigest(archive),
      rendererHashes: Object.fromEntries(Object.entries(rendererBytes).map(([name, bytes]) => [name, digest(bytes)])),
      verified: 'Package structure and bytes only; does not prove installation or business readiness.',
    });
  });

  it.each([pkg.main, '.vite/build/preload.cjs', manifestPath, rendererRoot + 'index.html', rendererRoot + 'assets/main-abc.js'])
    ('rejects the specifically missing required file %s', async name => {
      await rejects({[name]: null}, `"${path.normalize(name)}" was not found in this archive`);
    });

  it.each(['main.js', '.vite/build/main.js'])('rejects the incorrect main declaration %s before reading it', async main => {
    await rejects({'package.json': JSON.stringify({...pkg, main})}, 'Packaged main entry must be CJS.');
  });

  it.each([
    [pkg.main, 'assert(read(pkg.main).length > 0)'],
    ['.vite/build/preload.cjs', "assert(read('.vite/build/preload.cjs').length > 0)"],
    [rendererRoot + 'assets/main-abc.js', 'Empty renderer asset: assets/main-abc.js'],
  ])('rejects specifically empty required bytes at %s', async (name, message) => {
    await rejects({[name]: ''}, message);
  });

  it.each(['assets/../escape.js', '../escape.js', 'assets\\escape.js'])('rejects the raw invalid manifest path %s before normalizing it', async file => {
    await rejects({[manifestPath]: JSON.stringify({'index.html': {file, isEntry: true}})}, 'INVALID_RENDERER_ASSET');
  });

  it.each([
    ['.env', 'Environment file must not ship.'],
    ['config/.env.production', 'Environment file must not ship.'],
    ['.ssh/id_rsa', 'Private key must not ship.'],
    ['.ssh/id_ed25519.backup', 'Private key must not ship.'],
  ])('rejects the forbidden archive member %s after valid entry and asset checks', async (name, message) => {
    await rejects({[name]: 'SYNTHETIC-FORBIDDEN-FILE-NOT-A-REAL-SECRET'}, message);
  });
});
