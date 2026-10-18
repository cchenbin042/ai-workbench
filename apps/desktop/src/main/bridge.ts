import type { BrowserWindow, IpcMainInvokeEvent } from 'electron';
import { ipcMain } from 'electron';

import { PUBLIC_RPC_METHODS, type PublicRpcMethod } from '../shared/bridge';
import type { WorkbenchService } from './service-process';

const allowedMethods = new Set<string>(PUBLIC_RPC_METHODS);

export interface BridgeOptions {
  window: BrowserWindow;
  service: WorkbenchService;
  trustedOrigins: string[];
}

function fail(code: string): never {
  throw new Error(code);
}

function assertTrustedSender(event: IpcMainInvokeEvent, options: BridgeOptions): void {
  if (event.sender !== options.window.webContents) fail('UNTRUSTED_SENDER');
  if (event.senderFrame !== options.window.webContents.mainFrame) fail('UNTRUSTED_FRAME');

  const frameUrl = event.senderFrame?.url;
  if (!frameUrl) fail('UNTRUSTED_ORIGIN');

  let origin: string;
  try {
    origin = new URL(frameUrl).origin;
  } catch {
    fail('UNTRUSTED_ORIGIN');
  }
  if (!options.trustedOrigins.includes(origin)) fail('UNTRUSTED_ORIGIN');
}

export function registerBridge(options: BridgeOptions): () => void {
  const callHandler = async (
    event: IpcMainInvokeEvent,
    method: unknown,
    params: unknown,
  ): Promise<unknown> => {
    assertTrustedSender(event, options);

    if (typeof method !== 'string' || !allowedMethods.has(method)) {
      fail('METHOD_NOT_ALLOWED');
    }
    if (params !== undefined) {
      if (params === null || typeof params !== 'object' || Array.isArray(params)) {
        fail('INVALID_PARAMS');
      }
    }

    return options.service.request(
      method as PublicRpcMethod,
      (params ?? {}) as Record<string, unknown>,
    );
  };

  const onStatus = (status: unknown): void => {
    if (!options.window.isDestroyed()) {
      options.window.webContents.send('workbench:event', {
        type: 'service.status',
        status,
      });
    }
  };

  const onRpcEvent = (payload: unknown): void => {
    if (!options.window.isDestroyed()) {
      options.window.webContents.send('workbench:event', {
        type: 'rpc.event',
        payload,
      });
    }
  };

  ipcMain.handle('workbench:call', callHandler);
  options.service.on('status', onStatus);
  options.service.on('rpc-event', onRpcEvent);

  return () => {
    ipcMain.removeHandler('workbench:call');
    options.service.off('status', onStatus);
    options.service.off('rpc-event', onRpcEvent);
  };
}
