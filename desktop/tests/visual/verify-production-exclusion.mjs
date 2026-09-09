import {build} from 'vite';
import {createRequire} from 'node:module';
import {readFileSync, existsSync} from 'node:fs';
import {resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const marker = 'YIKE_VISUAL_TEST_ONLY_18794';
const failures = [];
let modules = 0;
// Real production entry and config; only its output location differs.
await build({configFile: resolve(root, 'vite.renderer.config.ts'), root: resolve(root, 'src/renderer'),
  build: {outDir: resolve(root, 'out/visual-production-check'), emptyOutDir: true, manifest: true},
  plugins: [{name: 'verify-no-visual-harness', generateBundle(_options, bundle) {
    for (const id of this.getModuleIds()) {modules++; if (/\/tests\/(visual|fixtures)\//.test(id.replaceAll('\\', '/'))) failures.push('module:' + id);}
    for (const [name, item] of Object.entries(bundle)) {
      const text = item.type === 'chunk' ? item.code : String(item.source);
      if (text.includes(marker) || /TEST-visual-review|TEST-monitor-paused/.test(text)) failures.push('asset:' + name);
    }
  }}],
});
const manifest = readFileSync(resolve(root, 'out/visual-production-check/.vite/manifest.json'), 'utf8');
const manifestHarnessReferences = (manifest.match(/tests\/visual|visual-harness|fixtures\.ts/g) || []).length;
if (manifestHarnessReferences) failures.push('manifest');
const require = createRequire(import.meta.url);
const asar = require('@electron/asar');
const archive = process.argv[2] ? resolve(process.argv[2]) : resolve(root, 'out/意客AI-darwin-arm64/意客AI.app/Contents/Resources/app.asar');
let archiveChecked = false;
if (existsSync(archive)) {
  archiveChecked = true;
  for (const name of asar.listPackage(archive)) {
    if (/tests\/visual|vite\.visual|visual-harness/.test(name)) failures.push('asar-path:' + name);
    if (/\.(js|cjs|mjs|html|json|css)$/.test(name)) {
      const text = asar.extractFile(archive, name.replace(/^\//, '')).toString();
      if (text.includes(marker) || /TEST-visual-review|TEST-monitor-paused/.test(text)) failures.push('asar-content:' + name);
    }
  }
}
console.log(JSON.stringify({productionGraphModules: modules, manifestHarnessReferences, existingAsarChecked: archiveChecked, failures}, null, 2));
if (failures.length) process.exitCode = 1;
