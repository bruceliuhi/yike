import {
  app,
  BrowserWindow,
  ipcMain,
  net,
  protocol,
  session,
  type WebContents
} from 'electron';
import {readFileSync} from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

import {
  DESKTOP_RUNTIME_NOT_READY,
  GET_RUNTIME_STATUS_CHANNEL
} from '../shared/contracts';
import {mainWindowOptions, rendererAssetForUrl} from './windowPolicy';

const APP_URL = 'yike://app/index.html';
const CONTENT_SECURITY_POLICY =
  "default-src 'self'; connect-src 'none'; object-src 'none'; frame-src 'none'";

protocol.registerSchemesAsPrivileged([
  {
    scheme: 'yike',
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true
    }
  }
]);

interface RendererManifestEntry {
  file?: unknown;
  css?: unknown;
  assets?: unknown;
}

function manifestAssets(rendererRoot: string): ReadonlySet<string> {
  const manifestPath = path.join(rendererRoot, '.vite', 'manifest.json');
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8')) as Record<
    string,
    RendererManifestEntry
  >;
  const assets = new Set<string>(['index.html']);

  for (const entry of Object.values(manifest)) {
    for (const value of [entry.file, entry.css, entry.assets]) {
      const candidates = Array.isArray(value) ? value : [value];
      for (const candidate of candidates) {
        if (
          typeof candidate !== 'string' ||
          candidate === '' ||
          candidate.includes('\\') ||
          candidate.includes('%') ||
          candidate.startsWith('/') ||
          /(?:^|\/)\.{1,2}(?:\/|$)/.test(candidate)
        ) {
          continue;
        }
        assets.add(candidate);
      }
    }
  }
  return assets;
}

async function registerRendererProtocol(rendererRoot: string): Promise<void> {
  const allowedAssets = manifestAssets(rendererRoot);
  await protocol.handle('yike', async (request) => {
    const asset = rendererAssetForUrl(request.url, allowedAssets);
    if (asset === null) {
      return new Response('Not found', {status: 404});
    }

    const response = await net.fetch(
      pathToFileURL(path.join(rendererRoot, ...asset.split('/'))).toString()
    );
    const headers = new Headers(response.headers);
    headers.set('Content-Security-Policy', CONTENT_SECURITY_POLICY);
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers
    });
  });
}

function rejectNavigation(contents: WebContents): void {
  contents.setWindowOpenHandler(() => ({action: 'deny'}));
  contents.on('will-navigate', (event, url) => {
    if (url !== APP_URL) {
      event.preventDefault();
    }
  });
  contents.on('will-redirect', (event) => event.preventDefault());
}

export function createMainWindow(): BrowserWindow {
  const preload = path.join(__dirname, 'preload.js');
  const window = new BrowserWindow(mainWindowOptions(preload));
  rejectNavigation(window.webContents);
  window.once('ready-to-show', () => window.show());
  void window.loadURL(APP_URL);
  return window;
}

app.whenReady().then(async () => {
  const rendererRoot = path.resolve(__dirname, '..', 'renderer', 'main_window');
  await registerRendererProtocol(rendererRoot);

  session.defaultSession.setPermissionCheckHandler(() => false);
  session.defaultSession.setPermissionRequestHandler(
    (_webContents, _permission, callback) => callback(false)
  );
  app.on('web-contents-created', (_event, contents) => {
    contents.on('will-attach-webview', (event) => event.preventDefault());
  });
  ipcMain.handle(GET_RUNTIME_STATUS_CHANNEL, () => DESKTOP_RUNTIME_NOT_READY);

  createMainWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
