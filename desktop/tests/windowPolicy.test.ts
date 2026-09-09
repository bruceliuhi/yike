import { describe, expect, it } from 'vitest';
import {mainWindowOptions, rendererAssetForUrl, isTrustedRuntimeSender, isTrustedRendererDocument} from '../src/main/windowPolicy';

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

  it('fits a 1280×720 desktop without a larger minimum window or forced zoom', () => {
    expect(mainWindowOptions('/preload.js')).toMatchObject({width: 1440, height: 1024, minWidth: 960, minHeight: 600});
    expect(mainWindowOptions('/preload.js', {width: 1280, height: 720})).toMatchObject({width: 1280, height: 720, minWidth: 960, minHeight: 600});
    expect(mainWindowOptions('/preload.js').webPreferences?.zoomFactor).toBeUndefined();
  });

  it('rejects IPC from subframes, foreign windows and non-app documents', () => {
    expect(isTrustedRuntimeSender('yike://app/index.html#opportunities', true, true)).toBe(true);
    expect(isTrustedRuntimeSender('yike://app/index.html', false, true)).toBe(false);
    expect(isTrustedRuntimeSender('yike://app/index.html', true, false)).toBe(false);
    expect(isTrustedRuntimeSender(undefined, true, true)).toBe(false);
    for (const url of ['https://app/index.html', 'yike://app/index.html?x=1', 'yike://app@evil/index.html', 'yike://app/assets/main.js', 'yike://app/index.html/extra']) {
      expect(isTrustedRendererDocument(url)).toBe(false);
    }
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
      'yike://app/not-in-manifest.js',
      'yike://app:80/index.html', 'yike://user:pass@app/index.html',
      'yike://app/index.html#fragment', 'yike://app/assets%2fapp-123.js'
    ]) {
      expect(rendererAssetForUrl(rejected, assets)).toBeNull();
    }
  });
});
