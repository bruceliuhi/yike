import {mkdtemp, rm, writeFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {spawn} from 'node:child_process';
import asar from '@electron/asar';
import electronPath from 'electron';

const archive = process.argv[2];
if (!archive?.endsWith('.asar')) throw new Error('Pass the packaged resources/app.asar path.');
const archivePath = path.resolve(archive);
const pkg = JSON.parse(asar.extractFile(archivePath, 'package.json').toString());
const temporary = await mkdtemp(path.join(os.tmpdir(), 'yike-packaged-smoke-'));
const script = `
const {app, dialog} = require('electron');
const assert = require('node:assert/strict');
const path = require('node:path');
app.setPath('userData', path.join(__dirname, 'user-data'));
const failures = [];
app.on('browser-window-created', (_event, window) => {
  // Verify actual packaged main/preload/renderer without disturbing the user's foreground app.
  window.show = () => {};
  window.webContents.on('preload-error', () => failures.push('PRELOAD_ERROR'));
  window.webContents.on('console-message', (_event, details) => {
    if (details.level === 'error') failures.push('RENDERER_CONSOLE_ERROR');
  });
  window.webContents.once('did-finish-load', async () => {
    try {
      const preferences = window.webContents.getLastWebPreferences();
      assert.equal(preferences.contextIsolation, true);
      assert.equal(preferences.nodeIntegration, false);
      assert.equal(preferences.sandbox, true);
      const deadline = Date.now() + 10000;
      let result;
      do {
        result = await window.webContents.executeJavaScript('(async () => ({url:location.href, title:document.title, body:document.body.innerText, bridge:!!window.yikeDesktop, info:await window.yikeDesktop?.getClientInfo(), invalid:await window.yikeDesktop?.requestApi({operation:"not-an-operation"}), unconfigured:await window.yikeDesktop?.requestApi({operation:"session.get"}), file:await window.yikeDesktop?.openExternal("file:///private/invalid"), clipboard:await window.yikeDesktop?.copyText("")}))()');
        if (result.bridge && result.body.includes('商机工作台')) break;
        await new Promise(resolve => setTimeout(resolve, 100));
      } while (Date.now() < deadline);
      assert.equal(result.url.split('#')[0], 'yike://app/index.html');
      assert.equal(result.bridge, true);
      assert.equal(result.info.serviceConfigured, false);
      assert.equal(result.info.version, ${JSON.stringify(pkg.version)});
      assert.equal(result.invalid.error, 'INVALID_API_REQUEST');
      assert.equal(result.unconfigured.error, 'SERVICE_NOT_CONFIGURED');
      assert.equal(result.file.error, 'INVALID_EXTERNAL_URL');
      assert.equal(result.clipboard.error, 'INVALID_CLIPBOARD_TEXT');
      assert(result.body.includes('商机工作台'), 'Packaged workbench did not render.');
      assert.equal(failures.length, 0, failures.join(','));
      let prompts = 0;
      dialog.showMessageBoxSync = (_window, options) => {
        assert.equal(options.title, '尚有未提交的更改');
        prompts++;
        return prompts === 1 ? 0 : 1;
      };
      await window.webContents.executeJavaScript('window.addEventListener("beforeunload", event => {event.preventDefault(); event.returnValue = "";});', true);
      app.quit();
      const closeDeadline = Date.now() + 2000;
      while (prompts === 0 && Date.now() < closeDeadline) await new Promise(resolve => setTimeout(resolve, 25));
      assert.equal(prompts, 1, 'Quit with unsaved edits must prompt.');
      assert.equal(window.isDestroyed(), false, 'Continue editing must keep the window alive.');
      const alive = await window.webContents.executeJavaScript('window.yikeDesktop.getClientInfo()');
      assert.equal(alive.serviceConfigured, false);
      app.once('will-quit', () => {
        assert.equal(prompts, 2, 'Discard and close must run the native confirmation.');
        console.log('PASS packaged main/preload/renderer: sandbox, custom protocol, application render, fixed IPC, unconfigured service, rejected native primitives, cancelled quit then normal confirmed quit.');
      });
      app.quit();
    } catch (error) {
      console.error(error instanceof Error ? error.message : 'PACKAGED_SMOKE_FAILED');
      app.exit(1);
    }
  });
});
require(${JSON.stringify(path.join(archivePath, pkg.main))});
`;
try {
  await writeFile(path.join(temporary, 'package.json'), JSON.stringify({name: 'yike-packaged-smoke', version: pkg.version, main: 'smoke.cjs'}));
  await writeFile(path.join(temporary, 'smoke.cjs'), script);
  const environment = {...process.env};
  delete environment.YIKE_SERVICE_URL;
  delete environment.YIKE_ALLOW_LOOPBACK_HTTP;
  const child = spawn(electronPath, [temporary], {stdio: 'inherit', env: environment});
  const timer = setTimeout(() => child.kill(), 25_000);
  const status = await new Promise((resolve, reject) => {
    child.once('error', reject);
    child.once('exit', (code, signal) => resolve(signal ? 1 : code ?? 1));
  });
  clearTimeout(timer);
  process.exitCode = status;
} finally { await rm(temporary, {recursive: true, force: true}); }
