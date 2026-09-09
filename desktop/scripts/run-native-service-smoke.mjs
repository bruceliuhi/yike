import {mkdtemp, rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import {builtinModules} from 'node:module';
import {build} from 'vite';
import electronPath from 'electron';

const root = fileURLToPath(new URL('..', import.meta.url));
const temporary = await mkdtemp(path.join(os.tmpdir(), 'yike-native-service-'));
try {
  await build({
    configFile: false, root, logLevel: 'warn',
    build: {
      outDir: temporary, emptyOutDir: false,
      lib: {entry: path.join(root, 'tests/nativeServiceSmoke.ts'), formats: ['cjs'], fileName: () => 'smoke.cjs'},
      rollupOptions: {external: ['electron', ...builtinModules, ...builtinModules.map(name => `node:${name}`)]}
    }
  });
  const child = spawn(electronPath, [path.join(temporary, 'smoke.cjs')], {
    stdio: 'inherit', env: {...process.env, YIKE_NATIVE_SMOKE_USER_DATA: path.join(temporary, 'user-data')}
  });
  const timer = setTimeout(() => child.kill(), 30_000);
  const status = await new Promise((resolve, reject) => {
    child.once('error', reject);
    child.once('exit', (code, signal) => resolve(signal ? 1 : code ?? 1));
  });
  clearTimeout(timer);
  process.exitCode = status;
} finally { await rm(temporary, {recursive: true, force: true}); }
