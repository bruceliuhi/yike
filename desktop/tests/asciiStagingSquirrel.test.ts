import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {chmodSync, copyFileSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmdirSync, rmSync, symlinkSync, unlinkSync, writeFileSync} from 'node:fs';
import fs from 'node:fs/promises';
import {syncBuiltinESMExports} from 'node:module';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {MakerSquirrel} from '@electron-forge/maker-squirrel';
import type {MakerOptions} from '@electron-forge/maker-base';
import config from '../forge.config';

const roots: string[] = [];
const links: string[] = [];
const actualTemp = realpathSync(os.tmpdir());
let root: string;
let stagingRoot: string;
let options: MakerOptions;

function maker() {
  const configured = (config.makers as MakerSquirrel[]).find(value => value.name === 'squirrel');
  if (!configured) throw new Error('Squirrel maker missing from Forge config');
  return configured.clone();
}

function artifacts(makeDir: string, arch = 'x64') {
  const directory = path.join(makeDir, 'squirrel.windows', arch);
  mkdirSync(directory, {recursive: true});
  return ['RELEASES', 'YikeAI-Setup.exe', 'YikeAI-0.2.0-full.nupkg'].map((name, index) => {
    const file = path.join(directory, name);
    writeFileSync(file, Buffer.from([0, 255, index, 10, 128]));
    return file;
  });
}

function junction(destination: string, target: string) {
  symlinkSync(target, destination, process.platform === 'win32' ? 'junction' : 'dir');
  links.push(destination);
}

beforeEach(() => {
  root = mkdtempSync(path.join(actualTemp, 'yike-squirrel-test-'));
  roots.push(root);
  stagingRoot = path.join(root, 'ASCII staging with spaces');
  mkdirSync(stagingRoot);
  vi.stubEnv('YIKE_SQUIRREL_STAGING_ROOT', stagingRoot);
  vi.spyOn(os, 'tmpdir').mockReturnValue(root);
  options = {
    dir: path.join(root, '意客AI-win32-x64'), makeDir: path.join(root, '中文工作区', 'out', 'make'),
    targetPlatform: 'win32', targetArch: 'x64', appName: '意客AI',
    packageJSON: {name: 'yike-ai-desktop', version: '0.2.0'},
    forgeConfig: config as MakerOptions['forgeConfig']
  };
});

afterEach(() => {
  vi.restoreAllMocks();
  syncBuiltinESMExports();
  vi.unstubAllEnvs();
  // Remove only test-created links themselves; never traverse their targets.
  for (const link of links.splice(0)) {
    if (existsSync(link) && lstatSync(link).isSymbolicLink()) unlinkSync(link);
  }
  for (const directory of roots.splice(0)) {
    if (!path.isAbsolute(directory) || path.dirname(directory) !== path.resolve(actualTemp) ||
        !path.basename(directory).startsWith('yike-squirrel-test-') ||
        realpathSync(directory).toLowerCase() !== path.resolve(directory).toLowerCase()) {
      throw new Error('Refusing to remove a path outside the generated test fixture.');
    }
    rmSync(directory, {recursive: true, force: true});
  }
});

describe('Squirrel ASCII output staging', () => {
  it('stages a Chinese workspace under an ASCII path, preserves config and returns identical bytes at the original output', async () => {
    const oldDirectory = path.join(options.makeDir, 'squirrel.windows', 'x64');
    mkdirSync(oldDirectory, {recursive: true});
    writeFileSync(path.join(oldDirectory, 'keep.txt'), 'prior user output');
    let temporary = '';
    let generated: Buffer[] = [];
    const native = vi.spyOn(MakerSquirrel.prototype, 'make').mockImplementation(async function (this: MakerSquirrel, input) {
      if (/[^\x20-\x7e]/.test(input.makeDir)) throw new Error('NATIVE_UNICODE_OUTPUT');
      temporary = input.makeDir;
      expect(path.dirname(temporary)).toBe(stagingRoot);
      expect(temporary).toContain(' ');
      expect({...input, makeDir: options.makeDir}).toEqual(options);
      expect(this.config).toMatchObject({name: 'YikeAI', authors: '星河科技', description: '意客AI商机工作台',
        exe: 'YikeAI.exe', setupExe: 'YikeAI-Setup.exe', noMsi: true});
      const files = artifacts(input.makeDir);
      generated = files.map(file => readFileSync(file));
      return files;
    });
    const instance = maker();
    await instance.prepareConfig('x64');
    const result = await instance.make(options);
    expect(native).toHaveBeenCalledTimes(1);
    expect(result).toEqual(['RELEASES', 'YikeAI-Setup.exe', 'YikeAI-0.2.0-full.nupkg'].map(name => path.join(oldDirectory, name)));
    result.forEach((file, index) => {
      const actual = readFileSync(file);
      expect(actual).toEqual(generated[index]);
      expect(createHash('sha256').update(actual).digest('hex')).toBe(createHash('sha256').update(generated[index]).digest('hex'));
    });
    expect(readFileSync(path.join(oldDirectory, 'keep.txt'), 'utf8')).toBe('prior user output');
    expect(existsSync(temporary)).toBe(false);
  });

  it('propagates native failure, preserves all original outputs and cleans only this run staging', async () => {
    const oldFiles = artifacts(options.makeDir);
    oldFiles.forEach(file => writeFileSync(file, 'previous successful build'));
    const before = oldFiles.map(file => readFileSync(file));
    const sibling = path.join(stagingRoot, 'another-run');
    mkdirSync(sibling);
    writeFileSync(path.join(sibling, 'keep.txt'), 'do not delete');
    let temporary = '';
    const failure = new Error('NATIVE_MAKE_FAILED');
    vi.spyOn(MakerSquirrel.prototype, 'make').mockImplementation(async input => {
      temporary = input.makeDir;
      artifacts(input.makeDir);
      throw failure;
    });
    await expect(maker().make(options)).rejects.toBe(failure);
    oldFiles.forEach((file, index) => expect(readFileSync(file)).toEqual(before[index]));
    expect(existsSync(temporary)).toBe(false);
    expect(readFileSync(path.join(sibling, 'keep.txt'), 'utf8')).toBe('do not delete');
  });

  it('uses an ASCII system temporary directory by default', async () => {
    vi.stubEnv('YIKE_SQUIRREL_STAGING_ROOT', undefined);
    vi.spyOn(MakerSquirrel.prototype, 'make').mockImplementation(async input => {
      expect(path.dirname(input.makeDir)).toBe(root);
      return artifacts(input.makeDir);
    });
    expect(await maker().make(options)).toHaveLength(3);
  });

  it.skipIf(process.platform !== 'win32')('restores the complete old artifact set when the real second copy fails on a read-only Setup.exe', async () => {
    const oldFiles = artifacts(options.makeDir);
    oldFiles.forEach((file, index) => writeFileSync(file, `previous successful artifact ${index}`));
    const before = oldFiles.map(file => readFileSync(file));
    const keep = path.join(path.dirname(oldFiles[0]), 'keep.txt');
    writeFileSync(keep, 'unrelated user file');
    chmodSync(oldFiles[1], 0o444);
    vi.spyOn(MakerSquirrel.prototype, 'make').mockImplementation(async input => artifacts(input.makeDir));
    try {
      await expect(maker().make(options)).rejects.toMatchObject({code: 'EPERM'});
      oldFiles.forEach((file, index) => expect(readFileSync(file)).toEqual(before[index]));
      expect(lstatSync(oldFiles[1]).mode & 0o222).toBe(0);
      expect(readFileSync(keep, 'utf8')).toBe('unrelated user file');
      expect(readdirSync(stagingRoot)).toEqual([]);
    } finally {
      // Restore only this synthetic test file's original attribute for fixture cleanup.
      chmodSync(oldFiles[1], 0o666);
    }
  });

  it('removes this run partial files after a real second copy failure with no historical artifacts', async () => {
    const finalDirectory = path.join(options.makeDir, 'squirrel.windows', 'x64');
    mkdirSync(finalDirectory, {recursive: true});
    const keep = path.join(finalDirectory, 'keep.txt');
    writeFileSync(keep, 'unrelated user file');
    let stagedFiles: string[] = [];
    vi.spyOn(MakerSquirrel.prototype, 'make').mockImplementation(async input => {
      stagedFiles = artifacts(input.makeDir);
      return stagedFiles;
    });
    const copy = fs.copyFile;
    let firstCopyCompleted = false;
    vi.spyOn(fs, 'copyFile').mockImplementation(async (source, destination, flags) => {
      await copy(source, destination, flags);
      if (destination === path.join(finalDirectory, 'RELEASES')) {
        firstCopyCompleted = true;
        // Remove the fixture's second source after validation, causing a real ENOENT on its copy.
        unlinkSync(stagedFiles[1]);
      }
    });
    syncBuiltinESMExports();
    await expect(maker().make(options)).rejects.toMatchObject({code: 'ENOENT'});
    expect(firstCopyCompleted).toBe(true);
    expect(readdirSync(finalDirectory)).toEqual(['keep.txt']);
    expect(readFileSync(keep, 'utf8')).toBe('unrelated user file');
    expect(readdirSync(stagingRoot)).toEqual([]);
  });

  it.skipIf(process.platform !== 'win32')('retains original backups and a recovery manifest when rollback itself fails', async () => {
    const oldFiles = artifacts(options.makeDir);
    oldFiles.forEach((file, index) => writeFileSync(file, `previous successful artifact ${index}`));
    const before = oldFiles.map(file => readFileSync(file));
    chmodSync(oldFiles[1], 0o444);
    vi.spyOn(MakerSquirrel.prototype, 'make').mockImplementation(async input => artifacts(input.makeDir));
    const copy = fs.copyFile;
    vi.spyOn(fs, 'copyFile').mockImplementation(async (source, destination, flags) => {
      await copy(source, destination, flags);
      // A real read-only failure on restoring the first file, after its successful forward copy.
      if (destination === oldFiles[0]) chmodSync(oldFiles[0], 0o444);
    });
    syncBuiltinESMExports();
    try {
      const failure = await maker().make(options).catch(error => error);
      expect(failure).toMatchObject({message: expect.stringContaining('SQUIRREL_COPY_ROLLBACK_FAILED'), recoveryDirectory: expect.any(String)});
      expect(failure.message).toContain(failure.recoveryDirectory);
      const manifest = JSON.parse(readFileSync(path.join(failure.recoveryDirectory, 'manifest.json'), 'utf8'));
      expect(manifest.schemaVersion).toBe(1);
      expect(manifest.artifacts).toHaveLength(3);
      manifest.artifacts.forEach((entry: {destination: string; backup: string; originalSha256: string}, index: number) => {
        expect(entry.destination).toBe(oldFiles[index]);
        const backup = readFileSync(path.join(failure.recoveryDirectory, entry.backup));
        expect(backup).toEqual(before[index]);
        expect(createHash('sha256').update(backup).digest('hex')).toBe(entry.originalSha256);
      });
      expect(readFileSync(oldFiles[1])).toEqual(before[1]);
      expect(readFileSync(oldFiles[2])).toEqual(before[2]);
    } finally {
      chmodSync(oldFiles[0], 0o666);
      chmodSync(oldFiles[1], 0o666);
    }
  });

  it('rejects a non-ASCII system temporary directory before the native maker even with explicit ASCII staging', async () => {
    vi.spyOn(os, 'tmpdir').mockReturnValue(path.join(root, '系统临时目录'));
    const native = vi.spyOn(MakerSquirrel.prototype, 'make').mockResolvedValue([]);
    await expect(maker().make(options)).rejects.toThrow('SQUIRREL_ASCII_SYSTEM_TEMP_REQUIRED');
    expect(native).not.toHaveBeenCalled();
    expect(readdirSync(stagingRoot)).toEqual([]);
  });

  it.each(['relative-root', '', 'missing', '中文暂存', 'traversal'])('rejects invalid staging root %s before native work', async value => {
    const invalid = value === 'relative-root' || value === '' ? value : value === 'traversal'
      ? `${stagingRoot}${path.sep}..${path.sep}existing` : path.join(root, value);
    if (value === 'traversal') {
      mkdirSync(path.join(root, 'existing'));
      expect(existsSync(invalid)).toBe(true);
      expect(invalid.split(path.sep)).toContain('..');
    }
    vi.stubEnv('YIKE_SQUIRREL_STAGING_ROOT', invalid);
    const native = vi.spyOn(MakerSquirrel.prototype, 'make').mockResolvedValue([]);
    await expect(maker().make(options)).rejects.toThrow(value === 'traversal' ? 'SQUIRREL_INVALID_STAGING_ROOT' : /SQUIRREL_.*(?:ROOT|PATH)/);
    expect(native).not.toHaveBeenCalled();
  });

  it('rejects a staging root with a junction ancestor', async () => {
    const linked = path.join(root, 'linked staging');
    junction(linked, stagingRoot);
    vi.stubEnv('YIKE_SQUIRREL_STAGING_ROOT', linked);
    const native = vi.spyOn(MakerSquirrel.prototype, 'make').mockResolvedValue([]);
    await expect(maker().make(options)).rejects.toThrow('SQUIRREL_UNSAFE_PATH');
    expect(native).not.toHaveBeenCalled();
  });

  it.each(['outside', 'directory', 'junction', 'duplicate', 'empty'])('rejects %s artifact results before any copy', async kind => {
    const outside = path.join(root, 'outside');
    mkdirSync(outside);
    const sentinel = path.join(outside, 'RELEASES');
    writeFileSync(sentinel, 'outside sentinel');
    vi.spyOn(MakerSquirrel.prototype, 'make').mockImplementation(async input => {
      const files = artifacts(input.makeDir);
      if (kind === 'outside') return [files[0], sentinel];
      if (kind === 'directory') return [files[0], path.dirname(files[0])];
      if (kind === 'duplicate') return [files[0], files[0]];
      if (kind === 'empty') return [];
      const linked = path.join(path.dirname(files[0]), 'linked');
      junction(linked, outside);
      return [files[0], path.join(linked, 'RELEASES')];
    });
    await expect(maker().make(options)).rejects.toThrow(/SQUIRREL_(?:INVALID_ARTIFACT|UNSAFE_PATH)/);
    expect(existsSync(options.makeDir)).toBe(false);
    expect(readdirSync(stagingRoot)).toEqual([]);
    expect(readFileSync(sentinel, 'utf8')).toBe('outside sentinel');
  });

  it('rejects a junction in the final output path without touching its target', async () => {
    const outside = path.join(root, 'outside output');
    mkdirSync(outside);
    mkdirSync(options.makeDir, {recursive: true});
    junction(path.join(options.makeDir, 'squirrel.windows'), outside);
    vi.spyOn(MakerSquirrel.prototype, 'make').mockImplementation(async input => artifacts(input.makeDir));
    await expect(maker().make(options)).rejects.toThrow('SQUIRREL_UNSAFE_PATH');
    expect(readdirSync(outside)).toEqual([]);
  });

  it('rejects an architecture that escapes the run directory before native work', async () => {
    options.targetArch = '../../outside' as MakerOptions['targetArch'];
    const native = vi.spyOn(MakerSquirrel.prototype, 'make').mockResolvedValue([]);
    await expect(maker().make(options)).rejects.toThrow('SQUIRREL_INVALID_ARCH');
    expect(native).not.toHaveBeenCalled();
  });

  it('refuses cleanup when the private staging root has been replaced by a junction', async () => {
    const outside = path.join(root, 'outside cleanup');
    mkdirSync(outside);
    const sentinel = path.join(outside, 'keep.txt');
    writeFileSync(sentinel, 'outside sentinel');
    vi.spyOn(MakerSquirrel.prototype, 'make').mockImplementation(async input => {
      expect(path.dirname(input.makeDir)).toBe(stagingRoot);
      // This directory was freshly generated by the adapter and is still empty.
      rmdirSync(input.makeDir);
      junction(input.makeDir, outside);
      return [sentinel];
    });
    await expect(maker().make(options)).rejects.toThrow('SQUIRREL_UNSAFE_PATH');
    expect(readFileSync(sentinel, 'utf8')).toBe('outside sentinel');
    expect(existsSync(options.makeDir)).toBe(false);
  });

  it.skipIf(process.platform !== 'win32')('edits a real Setup.exe in ASCII staging and copies Chinese product metadata intact', async () => {
    const desktop = fileURLToPath(new URL('../', import.meta.url));
    const vendor = path.join(desktop, 'node_modules', 'electron-winstaller', 'vendor');
    const editor = path.join(vendor, 'rcedit.exe');
    const original = path.join(vendor, 'Setup.exe');
    const hash = (file: string) => createHash('sha256').update(readFileSync(file)).digest('hex');
    let stagedHash = '';
    vi.spyOn(MakerSquirrel.prototype, 'make').mockImplementation(async input => {
      const files = artifacts(input.makeDir);
      copyFileSync(original, files[1]);
      const edit = spawnSync(editor, [files[1], '--set-version-string', 'ProductName', '意客AI商机工作台',
        '--set-file-version', '0.2.0', '--set-product-version', '0.2.0', '--set-icon', path.join(desktop, 'assets', 'yike.ico')],
      {encoding: 'utf8', windowsHide: true, timeout: 15000});
      expect(edit.error).toBeUndefined();
      expect(edit.status, edit.stdout + edit.stderr).toBe(0);
      stagedHash = hash(files[1]);
      expect(stagedHash).not.toBe(hash(original));
      return files;
    });
    const output = (await maker().make(options))[1];
    expect(hash(output)).toBe(stagedHash);
    const literal = output.replaceAll("'", "''");
    const metadata = spawnSync('powershell.exe', ['-NoLogo', '-NoProfile', '-NonInteractive', '-Command',
      `[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); (Get-Item -LiteralPath '${literal}').VersionInfo.ProductName`],
    {encoding: 'utf8', windowsHide: true, timeout: 15000});
    expect(metadata.status, metadata.stderr).toBe(0);
    expect(metadata.stdout.trim()).toBe('意客AI商机工作台');
    console.log('RCEDIT_STAGING_PROOF ' + JSON.stringify({toolSha256: hash(editor), sourceSetupSha256: hash(original),
      stagedSetupSha256: stagedHash, copiedSetupSha256: hash(output), productName: metadata.stdout.trim()}));
  }, 35000);
});
