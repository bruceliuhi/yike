import { describe, expect, it } from 'vitest';
import { mainWindowOptions, rendererAssetForUrl } from '../src/main/windowPolicy';

describe('desktop window boundary', () => {
  it('keeps renderer sandboxed and local', () => {
    const options = mainWindowOptions('/signed/preload.cjs');
    expect(options.webPreferences).toMatchObject({
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      preload: '/signed/preload.cjs'
    });
  });

  it('allows only the local app host and exact renderer manifest assets', () => {
    const assets = new Set(['index.html', 'assets/app-123.js']);

    expect(rendererAssetForUrl('yike://app/index.html', assets)).toBe('index.html');
    expect(rendererAssetForUrl('yike://app/assets/app-123.js', assets)).toBe(
      'assets/app-123.js'
    );
    for (const rejected of [
      'https://app/index.html',
      'yike://remote/index.html',
      'yike://app/../index.html',
      'yike://app/%2e%2e/index.html',
      'yike://app/index.html?redirect=https://example.com',
      'yike://app/not-in-manifest.js'
    ]) {
      expect(rendererAssetForUrl(rejected, assets)).toBeNull();
    }
  });
});
