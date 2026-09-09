import type { BrowserWindowConstructorOptions } from 'electron';

const APP_PROTOCOL = 'yike:';
const APP_HOST = 'app';
export const APP_URL = 'yike://app/index.html';

export function mainWindowOptions(
  preload: string,
  workArea?: {width: number; height: number}
): BrowserWindowConstructorOptions {
  const width = Math.min(1440, workArea?.width ?? 1440);
  const height = Math.min(1024, workArea?.height ?? 1024);
  return {
    width,
    height,
    minWidth: Math.min(960, width),
    minHeight: Math.min(600, height),
    show: false,
    title: '意客AI',
    backgroundColor: '#ffffff',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      webviewTag: false,
      navigateOnDragDrop: false,
      spellcheck: false,
      preload
    }
  };
}

/** Only the packaged top-level document may receive a preload capability. */
export function isTrustedRendererDocument(rawUrl: string): boolean {
  return rawUrl.split('#', 1)[0] === APP_URL;
}

export function isTrustedRuntimeSender(
  documentUrl: string | undefined,
  isMainFrame: boolean,
  belongsToMainWindow: boolean
): boolean {
  return isMainFrame && belongsToMainWindow && typeof documentUrl === 'string' &&
    isTrustedRendererDocument(documentUrl);
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
