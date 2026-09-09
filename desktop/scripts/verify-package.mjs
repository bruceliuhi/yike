import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import path from 'node:path';
import asar from '@electron/asar';
import {rendererManifestAssets} from '../src/main/rendererAssets.ts';

const archive = process.argv[2];
assert(archive && archive.endsWith('.asar'), 'Pass the packaged resources/app.asar path.');
const read = name => asar.extractFile(archive, name);
const pkg = JSON.parse(read('package.json').toString());
assert.equal(pkg.main, '.vite/build/main.cjs', 'Packaged main entry must be CJS.');
assert(read(pkg.main).length > 0);
assert(read('.vite/build/preload.cjs').length > 0);
const root = '.vite/renderer/main_window/';
const manifest = JSON.parse(read(root + '.vite/manifest.json').toString());
const assets = rendererManifestAssets(manifest);
const hashes = {};
for (const asset of assets) {
  const contents = read(root + asset);
  assert(contents.length > 0, `Empty renderer asset: ${asset}`);
  hashes[asset] = createHash('sha256').update(contents).digest('hex');
}
// Reject common environment and private-key files even if the packaging ignore rules regress.
for (const name of asar.listPackage(archive)) {
  assert(!/(?:^|[/\\])\.env(?:\.|$)/.test(name), 'Environment file must not ship.');
  assert(!/(?:^|[/\\])(?:id_rsa|id_ed25519)(?:\.|$)/.test(name), 'Private key must not ship.');
}
console.log(JSON.stringify({
  archive: path.resolve(archive), version: pkg.version, main: pkg.main,
  rendererAssetCount: assets.size,
  archiveSha256: createHash('sha256').update(readFileSync(archive)).digest('hex'),
  rendererHashes: hashes,
  verified: 'Package structure and bytes only; does not prove installation or business readiness.'
}, null, 2));
