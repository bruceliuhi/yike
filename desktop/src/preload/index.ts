import {contextBridge, ipcRenderer} from 'electron';
import {GET_DEVICE_IDENTITY_STATUS_CHANNEL, PREPARE_DEVICE_IDENTITY_CHANNEL} from '../shared/deviceIdentity';

import {
  GET_RUNTIME_STATUS_CHANNEL,
  GET_CLIENT_INFO_CHANNEL,
  REQUEST_API_CHANNEL,
  OPEN_EXTERNAL_CHANNEL,
  COPY_TEXT_CHANNEL,
  SAVE_EXPORT_CHANNEL,
  type ApiRequest,
  type ExportRequest,
  type YikeDesktopApi
} from '../shared/contracts';

const api: YikeDesktopApi = Object.freeze({
  getRuntimeStatus: () => ipcRenderer.invoke(GET_RUNTIME_STATUS_CHANNEL),
  getClientInfo: () => ipcRenderer.invoke(GET_CLIENT_INFO_CHANNEL),
  getDeviceIdentityStatus: () => ipcRenderer.invoke(GET_DEVICE_IDENTITY_STATUS_CHANNEL),
  prepareDeviceIdentity: (options = {}) => ipcRenderer.invoke(PREPARE_DEVICE_IDENTITY_CHANNEL, options),
  requestApi: (request: ApiRequest) => ipcRenderer.invoke(REQUEST_API_CHANNEL, request),
  openExternal: (url: string) => ipcRenderer.invoke(OPEN_EXTERNAL_CHANNEL, url),
  copyText: (text: string) => ipcRenderer.invoke(COPY_TEXT_CHANNEL, text),
  saveExport: (request: ExportRequest) => ipcRenderer.invoke(SAVE_EXPORT_CHANNEL, request)
});

contextBridge.exposeInMainWorld('yikeDesktop', api);
