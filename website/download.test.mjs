import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import assert from 'node:assert/strict';
import test from 'node:test';

test('download page provides both published installers', () => {
  const source = readFileSync(new URL('./src/main.js', import.meta.url), 'utf8');
  const page = source.split('\n').find(line => line.startsWith('function downloadPage()'));
  let html;
  runInNewContext(page + '\ndownloadPage();', {
    layout: value => { html = value; }, button: () => '',
  });
  assert.ok(html.includes('href="/downloads/windows/42d8402/YikeAI-Setup.exe"'));
  assert.ok(html.includes('href="/downloads/macos/9bd2c00/YikeAI-macOS-arm64-0.2.0.zip"'));
  assert.ok(html.includes('Apple 芯片'));
  assert.ok(!html.includes('申请安装包 / 试用码'));
});

test('download buttons wrap on narrow screens', () => {
  const css = readFileSync(new URL('./src/styles.css', import.meta.url), 'utf8');
  assert.match(css, /\.download-actions\s*\{[^}]*flex-wrap:\s*wrap/);
});
