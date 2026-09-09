import {mkdtemp, mkdir, rm, symlink, writeFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {build, type UserConfig} from 'vite';
import {expect, test} from 'vitest';
import rendererConfig from '../vite.renderer.config';

// Reproduce the linked dependency layout that once let Forge emit separate
// React instances for application hooks and react-dom's dispatcher.
test('linked dependencies keep one React dispatcher in the production renderer', async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'yike-react-singleton-'));
  const dependencies = path.resolve(fileURLToPath(new URL('../node_modules', import.meta.url)));
  try {
    await mkdir(path.join(directory, 'node_modules'));
    const linkType = process.platform === 'win32' ? 'junction' : 'dir';
    for (const name of ['react', 'react-dom', 'scheduler']) {
      await symlink(path.join(dependencies, name), path.join(directory, 'node_modules', name), linkType);
    }
    await symlink(path.join(directory, 'node_modules'), path.join(directory, 'node_modules', 'node_modules'), linkType);
    await writeFile(path.join(directory, 'index.html'), '<div id="root"></div><script type="module" src="/main.js"></script>');
    await writeFile(path.join(directory, 'main.js'), `
      import {createElement, useState} from 'react';
      import {createRoot} from 'react-dom/client';
      function App() { const [value] = useState('ready'); return createElement('h1', null, value); }
      createRoot(document.getElementById('root')).render(createElement(App));
    `);
    async function reactModules(resolve: UserConfig['resolve']) {
      let modules: string[] = [];
      await build({
        configFile: false, root: directory, logLevel: 'silent', resolve,
        define: {'process.env.NODE_ENV': JSON.stringify('production')},
        build: {write: false},
        plugins: [{name: 'capture-react-dispatchers', generateBundle() {
          modules = [...this.getModuleIds()].filter(id => /\/react\/cjs\/react\.production\.js$/.test(id.replaceAll('\\', '/')));
        }}],
      });
      return modules;
    }
    expect((await reactModules({preserveSymlinks: true})).length).toBeGreaterThan(1);
    expect(await reactModules((rendererConfig as UserConfig).resolve)).toHaveLength(1);
  } finally {
    await rm(directory, {recursive: true, force: true});
  }
}, 20_000);
