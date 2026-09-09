import type { BrowserWindowConstructorOptions } from 'electron';

const APP_PROTOCOL = 'yike:';
const APP_HOST = 'app';

export function mainWindowOptions(preload: string): BrowserWindowConstructorOptions {
  return {
    width: 1180,
    height: 760,
    minWidth: 960,
    minHeight: 640,
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      preload
    }
  };
}

export function rendererAssetForUrl(
  rawUrl: string,
  allowedAssets: ReadonlySet<string>
): string | null {
  if (
    rawUrl.includes('\\') ||
    rawUrl.includes('%') ||
    /(?:^|\/)\.{1,2}(?:\/|$)/.test(rawUrl)
  ) {
    return null;
  }

  let url: URL;
  try {
    url = new URL(rawUrl);
  } catch {
    return null;
  }

  if (
    url.protocol !== APP_PROTOCOL ||
    url.hostname !== APP_HOST ||
    url.username !== '' ||
    url.password !== '' ||
    url.port !== '' ||
    url.search !== '' ||
    url.hash !== ''
  ) {
    return null;
  }

  const asset = url.pathname.slice(1);
  if (url.pathname !== `/${asset}` || asset === '' || !allowedAssets.has(asset)) {
    return null;
  }
  return asset;
}
