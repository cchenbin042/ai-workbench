import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron';

import {
  PUBLIC_RPC_METHODS,
  type BridgeEvent,
  type PublicRpcMethod,
  type WorkbenchBridge,
} from '../shared/bridge';

const allowedMethods = new Set<string>(PUBLIC_RPC_METHODS);

const bridge: WorkbenchBridge = {
  async call(method, params = {}) {
    if (typeof method !== 'string' || !allowedMethods.has(method)) {
      throw new Error(`METHOD_NOT_ALLOWED: ${String(method)}`);
    }
    if (params === null || typeof params !== 'object' || Array.isArray(params)) {
      throw new Error('INVALID_PARAMS');
    }
    return ipcRenderer.invoke('workbench:call', method as PublicRpcMethod, params);
  },

  async getStatus() {
    return ipcRenderer.invoke('workbench:get-status');
  },

  async restartService() {
    return ipcRenderer.invoke('workbench:restart-service');
  },

  subscribe(listener) {
    if (typeof listener !== 'function') {
      throw new TypeError('listener must be a function');
    }
    const handler = (_event: IpcRendererEvent, payload: BridgeEvent): void => listener(payload);
    ipcRenderer.on('workbench:event', handler);
    return () => {
      ipcRenderer.removeListener('workbench:event', handler);
    };
  },

  runtime: {
    platform: process.platform,
    electron: process.versions.electron ?? '',
    chrome: process.versions.chrome ?? '',
    node: process.versions.node ?? '',
  },
};

contextBridge.exposeInMainWorld('workbench', bridge);
