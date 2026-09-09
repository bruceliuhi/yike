import {mkdtempSync, mkdirSync, writeFileSync, symlinkSync, rmSync} from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {afterEach, describe, expect, it} from 'vitest';
import {CONTENT_SECURITY_POLICY, rendererManifestAssets, loadRendererAssets} from '../src/main/rendererAssets';

const manifest = {
  'index.html': {file: 'assets/index-abc.js', isEntry: true, css: ['assets/index-abc.css'], assets: ['assets/yike-logo.png']},
  'lazy.ts': {file: 'assets/lazy-def.js', isDynamicEntry: true}
};
const temporary: string[] = [];
afterEach(() => { for (const dir of temporary.splice(0)) rmSync(dir, {recursive: true, force: true}); });

describe('packaged renderer manifest', () => {
  it('includes hashed JS, CSS, imported brand image and lazy chunks but no other files', () => {
    expect([...rendererManifestAssets(manifest)]).toEqual(['index.html', 'assets/index-abc.js', 'assets/index-abc.css', 'assets/yike-logo.png', 'assets/lazy-def.js']);
    expect(CONTENT_SECURITY_POLICY).toContain("connect-src 'none'");
    expect(CONTENT_SECURITY_POLICY).not.toContain('unsafe');
  });

  it('fails closed for malformed manifest or directory traversal paths', () => {
    for (const value of [null, [], {}, {main: {file: 'assets/no-entry.js'}}]) {
      expect(() => rendererManifestAssets(value)).toThrow();
    }
    for (const file of ['../secret', '/assets/main.js', 'assets/../secret.js', 'assets/a%2f.js', 'assets/a?token.js', 'assets/a\\b.js', 'assets//b.js']) {
      expect(() => rendererManifestAssets({main: {file, isEntry: true}})).toThrow();
    }
  });

  it('fails startup when an allowlisted asset is absent or points outside the renderer tree', () => {
    const root = mkdtempSync(path.join(os.tmpdir(), 'yike-assets-')); temporary.push(root);
    mkdirSync(path.join(root, '.vite')); mkdirSync(path.join(root, 'assets'));
    writeFileSync(path.join(root, '.vite', 'manifest.json'), JSON.stringify({main: {file: 'assets/main.js', isEntry: true}}));
    writeFileSync(path.join(root, 'index.html'), 'ok');
    expect(() => loadRendererAssets(root)).toThrow();
    const outside = mkdtempSync(path.join(os.tmpdir(), 'yike-outside-')); temporary.push(outside);
    // Directory junctions do not require the Windows symlink privilege.
    rmSync(path.join(root, 'assets'), {recursive: true});
    writeFileSync(path.join(outside, 'main.js'), 'private');
    symlinkSync(outside, path.join(root, 'assets'), process.platform === 'win32' ? 'junction' : 'dir');
    expect(() => loadRendererAssets(root)).toThrow('INVALID_RENDERER_RESOURCE');
  });
});
