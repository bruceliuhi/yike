import {contextBridge, ipcRenderer} from 'electron';

import {
  GET_RUNTIME_STATUS_CHANNEL,
  type YikeDesktopApi
} from '../shared/contracts';

const api: YikeDesktopApi = Object.freeze({
  getRuntimeStatus: () => ipcRenderer.invoke(GET_RUNTIME_STATUS_CHANNEL)
});

contextBridge.exposeInMainWorld('yikeDesktop', api);
