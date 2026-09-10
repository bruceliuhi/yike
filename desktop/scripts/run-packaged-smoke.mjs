import {mkdtemp, readFile, rm, writeFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {spawn} from 'node:child_process';
import asar from '@electron/asar';
import electronPath from 'electron';
import {inspectWorkbench, isRendererConsoleError, workbenchFailure} from './packaged-smoke-policy.mjs';

const archive = process.argv[2];
if (!archive?.endsWith('.asar')) throw new Error('Pass the packaged resources/app.asar path.');
const archivePath = path.resolve(archive);
const pkg = JSON.parse(asar.extractFile(archivePath, 'package.json').toString());
const temporary = await mkdtemp(path.join(os.tmpdir(), 'yike-packaged-smoke-'));
const rendererProbe = '(async () => ({url:location.href, title:document.title, workbench:(' + inspectWorkbench.toString() + ')(document), bridge:!!window.yikeDesktop, info:await window.yikeDesktop?.getClientInfo(), invalid:await window.yikeDesktop?.requestApi({operation:"not-an-operation"}), unconfigured:await window.yikeDesktop?.requestApi({operation:"session.get"}), file:await window.yikeDesktop?.openExternal("file:///private/invalid"), clipboard:await window.yikeDesktop?.copyText("")}))()';
const script = `
const {app, dialog} = require('electron');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs/promises');
const {writeFileSync} = require('node:fs');
const isRendererConsoleError = ${isRendererConsoleError.toString()};
const workbenchFailure = ${workbenchFailure.toString()};
app.setPath('userData', path.join(__dirname, 'user-data'));
const failures = [];
app.on('browser-window-created', (_event, window) => {
  // Verify actual packaged main/preload/renderer without disturbing the user's foreground app.
  window.show = () => {};
  window.webContents.on('preload-error', () => failures.push('PRELOAD_ERROR'));
  window.webContents.on('render-process-gone', () => failures.push('RENDERER_PROCESS_GONE'));
  window.webContents.on('console-message', (...args) => {
    if (isRendererConsoleError(...args)) failures.push('RENDERER_CONSOLE_ERROR');
  });
  window.webContents.once('did-finish-load', async () => {
    try {
      const preferences = window.webContents.getLastWebPreferences();
      assert.equal(preferences.contextIsolation, true);
      assert.equal(preferences.nodeIntegration, false);
      assert.equal(preferences.sandbox, true);
      const deadline = Date.now() + 10000;
      let result;
      let stable = 0;
      do {
        result = await window.webContents.executeJavaScript(${JSON.stringify(rendererProbe)});
        assert.equal(failures.length, 0, failures.join(','));
        assert.notEqual(workbenchFailure(result.workbench), 'PACKAGED_PAGE_ERROR', 'PACKAGED_PAGE_ERROR');
        stable = result.bridge && workbenchFailure(result.workbench) === null ? stable + 1 : 0;
        if (stable >= 3) break;
        await new Promise(resolve => setTimeout(resolve, 100));
      } while (Date.now() < deadline);
      assert.equal(result.url.split('#')[0], 'yike://app/index.html');
      assert.equal(result.bridge, true);
      assert.equal(result.info.serviceConfigured, false);
      assert.equal(result.info.version, ${JSON.stringify(pkg.version)});
      assert.equal(result.invalid.error, 'INVALID_API_REQUEST');
      assert.equal(result.unconfigured.error, 'SERVICE_NOT_CONFIGURED');
      assert.deepEqual(await window.webContents.executeJavaScript('window.yikeDesktop.executionCommand({action:"LIST"})'),
        {state: 'SERVICE_UNAVAILABLE'}, 'Fixed execution IPC must preserve unconfigured-service state.');
      assert.equal(result.file.error, 'INVALID_EXTERNAL_URL');
      assert.equal(result.clipboard.error, 'INVALID_CLIPBOARD_TEXT');
      assert.equal(workbenchFailure(result.workbench), null, workbenchFailure(result.workbench));
      assert(stable >= 3, 'PACKAGED_WORKBENCH_NOT_STABLE');
      assert.equal(failures.length, 0, failures.join(','));
      // Save dialogs are substituted only inside this isolated smoke process.
      // The real packaged IPC, validation, and disk writer still execute.
      let exportDialogs = 0;
      dialog.showSaveDialog = async (_window, options) => {
        exportDialogs++;
        assert.equal(options.defaultPath, exportDialogs === 2 ? 'TEST-backup.yike-backup.json' : 'TEST-export.csv');
        assert.deepEqual(options.filters[0].extensions, [exportDialogs === 2 ? 'json' : 'csv']);
        return exportDialogs === 3 ? {canceled: true} : {canceled: false, filePath: path.join(__dirname, options.defaultPath)};
      };
      const invokeExport = request => window.webContents.executeJavaScript('window.yikeDesktop.saveExport(' + JSON.stringify(request) + ')');
      const csvExport = {format: 'csv', name: 'TEST-export', content: 'TEST,export'};
      assert.deepEqual(await invokeExport(csvExport), {status: 'saved'});
      assert.equal(await fs.readFile(path.join(__dirname, 'TEST-export.csv'), 'utf8'), csvExport.content);
      const backupExport = {format: 'backup-json', name: 'TEST-backup', content: JSON.stringify({test: true})};
      assert.deepEqual(await invokeExport(backupExport), {status: 'saved'});
      assert.deepEqual(JSON.parse(await fs.readFile(path.join(__dirname, 'TEST-backup.yike-backup.json'), 'utf8')), {test: true});
      assert.deepEqual(await invokeExport(csvExport), {status: 'cancelled'});
      assert.deepEqual(await invokeExport({...csvExport, name: '../rejected'}), {status: 'error', error: 'INVALID_EXPORT_REQUEST'});
      assert.equal(exportDialogs, 3);
      const finalWorkbench = await window.webContents.executeJavaScript(${JSON.stringify('(' + inspectWorkbench.toString() + ')(document)')});
      assert.equal(workbenchFailure(finalWorkbench), null, workbenchFailure(finalWorkbench));
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
        try {
          assert.equal(prompts, 2, 'Discard and close must run the native confirmation.');
          assert.equal(failures.length, 0, failures.join(','));
          writeFileSync(path.join(__dirname, 'completed.json'), JSON.stringify({passed: true}));
        } catch (error) {
          console.error(error instanceof Error ? error.message : 'PACKAGED_SMOKE_FAILED');
          app.exit(1);
          return;
        }
        console.log('PASS packaged main/preload/renderer: sandbox, custom protocol, application render, fixed IPC, unconfigured service, rejected native primitives, CSV/backup export actual temporary-file writes and cancellation, cancelled quit then normal confirmed quit.');
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
  let completed = false;
  if (status === 0) {
    try { completed = JSON.parse(await readFile(path.join(temporary, 'completed.json'), 'utf8')).passed === true; }
    catch { /* A clean early exit is not successful verification. */ }
  }
  if (status === 0 && !completed) console.error('PACKAGED_SMOKE_INCOMPLETE');
  process.exitCode = status === 0 && completed ? 0 : 1;
} finally { await rm(temporary, {recursive: true, force: true}); }
