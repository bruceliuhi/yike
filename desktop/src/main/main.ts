import {
  app, BrowserWindow, clipboard, dialog, ipcMain, Menu, net, protocol, screen, session, shell,
  type IpcMainInvokeEvent, type WebContents
} from 'electron';
import squirrelStartup from 'electron-squirrel-startup';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {
  DESKTOP_RUNTIME_NOT_READY, GET_RUNTIME_STATUS_CHANNEL,
  GET_CLIENT_INFO_CHANNEL, REQUEST_API_CHANNEL, OPEN_EXTERNAL_CHANNEL, COPY_TEXT_CHANNEL
} from '../shared/contracts';
import {CONTENT_SECURITY_POLICY, loadRendererAssets} from './rendererAssets';
import {
  APP_URL, isTrustedRendererDocument, isTrustedRuntimeSender,
  mainWindowOptions, rendererAssetForUrl
} from './windowPolicy';
import {createServiceClient, configuredService} from './serviceClient';
import {validatedExternalUrl, validClipboardText} from './servicePolicy';

protocol.registerSchemesAsPrivileged([
  {scheme: 'yike', privileges: {standard: true, secure: true, supportFetchAPI: true}}
]);

let mainWindow: BrowserWindow | null = null;
let quitting = false;
let startupFailed = false;

function failStartup(): void {
  if (quitting || startupFailed) return;
  startupFailed = true;
  console.error('YIKE_DESKTOP_LOAD_FAILED');
  dialog.showErrorBox('意客AI 无法启动', '客户端资源未能正常加载。请重新安装或联系支持。');
  app.quit();
}

async function registerRendererProtocol(rendererRoot: string): Promise<void> {
  const allowedAssets = loadRendererAssets(rendererRoot);
  await protocol.handle('yike', async (request) => {
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return new Response('Method not allowed', {status: 405, headers: {Allow: 'GET, HEAD'}});
    }
    const asset = rendererAssetForUrl(request.url, allowedAssets);
    if (asset === null) return new Response('Not found', {status: 404});
    try {
      const response = await net.fetch(pathToFileURL(path.join(rendererRoot, ...asset.split('/'))).toString());
      const headers = new Headers(response.headers);
      headers.set('Content-Security-Policy', CONTENT_SECURITY_POLICY);
      headers.set('X-Content-Type-Options', 'nosniff');
      headers.set('Cache-Control', 'no-store');
      return new Response(request.method === 'HEAD' ? null : response.body, {
        status: response.status, statusText: response.statusText, headers
      });
    } catch {
      return new Response('Resource unavailable', {status: 404});
    }
  });
}

function rejectNavigation(contents: WebContents): void {
  contents.setWindowOpenHandler(() => ({action: 'deny'}));
  contents.on('will-navigate', (event, url) => {
    if (!isTrustedRendererDocument(url)) event.preventDefault();
  });
  contents.on('will-redirect', (event) => event.preventDefault());
  contents.on('will-attach-webview', (event) => event.preventDefault());
}

export function createMainWindow(): BrowserWindow {
  const window = new BrowserWindow(mainWindowOptions(
    path.join(__dirname, 'preload.cjs'), screen.getPrimaryDisplay().workAreaSize
  ));
  mainWindow = window;
  rejectNavigation(window.webContents);
  window.once('ready-to-show', () => {
    if (!quitting && !window.isDestroyed()) window.show();
  });
  window.once('closed', () => { if (mainWindow === window) mainWindow = null; });
  window.webContents.on('will-prevent-unload', event => {
    const discard = dialog.showMessageBoxSync(window, {
      type: 'question', buttons: ['继续编辑', '放弃更改并关闭'], defaultId: 0, cancelId: 0,
      title: '尚有未提交的更改', message: '是否放弃当前未提交的更改并关闭窗口？', noLink: true
    }) === 1;
    if (discard) event.preventDefault(); // Electron uses preventDefault here to permit the unload.
    else quitting = false;
  });
  window.webContents.on('render-process-gone', (_event, details) => {
    if (details.reason !== 'clean-exit' && !quitting) failStartup();
  });
  window.webContents.on('did-fail-load', (_event, _code, _description, _url, isMainFrame) => {
    if (isMainFrame && !window.isDestroyed()) failStartup();
  });
  void window.loadURL(APP_URL).catch(() => {
    if (!window.isDestroyed()) failStartup();
  });
  return window;
}

function trustedSender(event: IpcMainInvokeEvent): void {
  const frame = event.senderFrame;
  if (!isTrustedRuntimeSender(
    frame?.url, frame !== null && frame === event.sender.mainFrame,
    mainWindow !== null && !mainWindow.isDestroyed() && event.sender === mainWindow.webContents
  )) throw new Error('UNTRUSTED_DESKTOP_SENDER');
}

function installMenu(): void {
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    ...(process.platform === 'darwin' ? [{role: 'appMenu' as const, label: '意客AI'}] : []),
    {role: 'fileMenu'}, {role: 'editMenu'},
    {label: '显示', submenu: [
      {role: 'resetZoom'}, {role: 'zoomIn'}, {role: 'zoomOut'},
      {type: 'separator'}, {role: 'togglefullscreen'}
    ]},
    {role: 'windowMenu'}
  ]));
}

async function startApplication(): Promise<void> {
  await app.whenReady();
  await registerRendererProtocol(path.resolve(__dirname, '..', 'renderer', 'main_window'));
  session.defaultSession.setPermissionCheckHandler(() => false);
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  session.defaultSession.on('will-download', event => event.preventDefault());
  const serviceSession = session.fromPartition('yike-service'); // No persist: prefix: cookies stay in memory.
  serviceSession.setPermissionCheckHandler(() => false);
  serviceSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  const baseUrl = configuredService(process.env.YIKE_SERVICE_URL, {
    packaged: app.isPackaged,
    allowLoopbackHttp: process.env.YIKE_ALLOW_LOOPBACK_HTTP === '1'
  });
  const service = createServiceClient({
    baseUrl,
    fetch: (url, options) => serviceSession.fetch(url, options),
    clearSession: () => serviceSession.clearStorageData()
  });
  ipcMain.handle(GET_RUNTIME_STATUS_CHANNEL, event => {
    trustedSender(event);
    return DESKTOP_RUNTIME_NOT_READY;
  });
  ipcMain.handle(GET_CLIENT_INFO_CHANNEL, event => {
    trustedSender(event);
    return {version: app.getVersion(), platform: process.platform, serviceConfigured: baseUrl !== null};
  });
  ipcMain.handle(REQUEST_API_CHANNEL, (event, request: unknown) => {
    trustedSender(event);
    return service.request(request);
  });
  ipcMain.handle(OPEN_EXTERNAL_CHANNEL, async (event, input: unknown) => {
    trustedSender(event);
    const url = validatedExternalUrl(input);
    if (url === null) return {ok: false, error: 'INVALID_EXTERNAL_URL'};
    try { await shell.openExternal(url); return {ok: true}; }
    catch { return {ok: false, error: 'OPEN_EXTERNAL_FAILED'}; }
  });
  ipcMain.handle(COPY_TEXT_CHANNEL, (event, input: unknown) => {
    trustedSender(event);
    if (!validClipboardText(input)) return {ok: false, error: 'INVALID_CLIPBOARD_TEXT'};
    try { clipboard.writeText(input); return {ok: true}; }
    catch { return {ok: false, error: 'COPY_TEXT_FAILED'}; }
  });
  installMenu();
  createMainWindow();
  app.on('activate', () => {
    if (!quitting && !startupFailed && BrowserWindow.getAllWindows().length === 0) createMainWindow();
  });
}

app.on('before-quit', () => { quitting = true; });
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
if (squirrelStartup || !app.requestSingleInstanceLock()) {
  app.quit();
} else {
  if (process.platform === 'win32') app.setAppUserModelId('com.squirrel.YikeAI.YikeAI');
  app.on('second-instance', () => {
    if (mainWindow !== null && !mainWindow.isDestroyed()) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });
  void startApplication().catch(failStartup);
}
