import {existsSync} from 'node:fs';
import {mkdtemp, rm, writeFile} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import os from 'node:os';
import path from 'node:path';
import asar from '@electron/asar';
import {describe, expect, it} from 'vitest';

const badArchive = process.env.YIKE_TEST_BROKEN_ASAR;
const runNativeFixtures = !!process.env.YIKE_TEST_PACKAGED_SMOKE || !!badArchive && existsSync(badArchive);
const root = fileURLToPath(new URL('../', import.meta.url));

describe('packaged smoke negative artifact regression', () => {
  it.skipIf(!badArchive || !existsSync(badArchive))('rejects a real package whose React page renders the error boundary', () => {
    const result = spawnSync(process.execPath, ['scripts/run-packaged-smoke.mjs', badArchive], {
      cwd: root, encoding: 'utf8', timeout: 35_000,
    });
    expect(result.error).toBeUndefined();
    expect(result.status, 'A broken React archive must not pass packaged smoke.').not.toBe(0);
    expect(result.stdout).not.toContain('PASS packaged main/preload/renderer');
    expect(result.stderr).toMatch(/RENDERER_CONSOLE_ERROR|PACKAGED_PAGE_ERROR/);
  }, 40_000);

  it.skipIf(!runNativeFixtures)('does not accept exit zero before any packaged checks completed', async () => {
    const fixture = await mkdtemp(path.join(os.tmpdir(), 'yike-early-exit-fixture-'));
    const archive = fixture + '.asar';
    try {
      await writeFile(path.join(fixture, 'package.json'), JSON.stringify({name: 'test-early-exit', version: '0.0.0', main: 'main.cjs'}));
      await writeFile(path.join(fixture, 'main.cjs'), "const {app}=require('electron'); app.whenReady().then(()=>app.exit(0));");
      await asar.createPackage(fixture, archive);
      const result = spawnSync(process.execPath, ['scripts/run-packaged-smoke.mjs', archive], {
        cwd: root, encoding: 'utf8', timeout: 35_000,
      });
      expect(result.error).toBeUndefined();
      expect(result.status).toBe(1);
      expect(result.stderr).toContain('PACKAGED_SMOKE_INCOMPLETE');
      expect(result.stdout).not.toContain('PASS packaged main/preload/renderer');
    } finally {
      await rm(archive, {force: true});
      await rm(fixture, {recursive: true, force: true});
    }
  }, 40_000);

  it.skipIf(!runNativeFixtures)('captures console.error from an actual Electron renderer', async () => {
    const fixture = await mkdtemp(path.join(os.tmpdir(), 'yike-console-error-fixture-'));
    const archive = fixture + '.asar';
    try {
      await writeFile(path.join(fixture, 'package.json'), JSON.stringify({name: 'test-console-error', version: '0.0.0', main: 'main.cjs'}));
      await writeFile(path.join(fixture, 'main.cjs'), `
        const {app, BrowserWindow} = require('electron');
        app.whenReady().then(() => {
          const window = new BrowserWindow({show:false, webPreferences:{contextIsolation:true, nodeIntegration:false, sandbox:true}});
          window.loadURL('data:text/html,' + encodeURIComponent('<script>console.error("TEST renderer error probe")</script>'));
        });
      `);
      await asar.createPackage(fixture, archive);
      const result = spawnSync(process.execPath, ['scripts/run-packaged-smoke.mjs', archive], {
        cwd: root, encoding: 'utf8', timeout: 35_000,
      });
      expect(result.error).toBeUndefined();
      expect(result.status).toBe(1);
      expect(result.stderr).toContain('RENDERER_CONSOLE_ERROR');
      expect(result.stdout).not.toContain('PASS packaged main/preload/renderer');
    } finally {
      await rm(archive, {force: true});
      await rm(fixture, {recursive: true, force: true});
    }
  }, 40_000);
});
