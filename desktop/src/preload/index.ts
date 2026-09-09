import {contextBridge, ipcRenderer} from 'electron';

import {
  GET_RUNTIME_STATUS_CHANNEL,
  GET_CLIENT_INFO_CHANNEL,
  REQUEST_API_CHANNEL,
  OPEN_EXTERNAL_CHANNEL,
  COPY_TEXT_CHANNEL,
  type ApiRequest,
  type YikeDesktopApi
} from '../shared/contracts';

const api: YikeDesktopApi = Object.freeze({
  getRuntimeStatus: () => ipcRenderer.invoke(GET_RUNTIME_STATUS_CHANNEL),
  getClientInfo: () => ipcRenderer.invoke(GET_CLIENT_INFO_CHANNEL),
  requestApi: (request: ApiRequest) => ipcRenderer.invoke(REQUEST_API_CHANNEL, request),
  openExternal: (url: string) => ipcRenderer.invoke(OPEN_EXTERNAL_CHANNEL, url),
  copyText: (text: string) => ipcRenderer.invoke(COPY_TEXT_CHANNEL, text)
});

contextBridge.exposeInMainWorld('yikeDesktop', api);
