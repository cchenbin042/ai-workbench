import type { BrowserWindow, IpcMainInvokeEvent } from 'electron';
import { ipcMain } from 'electron';

import { checkCallRequest, checkSender, type SenderRequest } from '../shared/ipc-policy';
import type { WorkbenchService } from './service-process';

export interface BridgeOptions {
  window: BrowserWindow;
  service: WorkbenchService;
  trustedOrigins: string[];
}

function senderRequest(event: IpcMainInvokeEvent, options: BridgeOptions): SenderRequest {
  return {
    senderIsMainWindow: event.sender === options.window.webContents,
    frameIsMainFrame: event.senderFrame === options.window.webContents.mainFrame,
    frameUrl: event.senderFrame?.url ?? null,
  };
}

function assertSender(event: IpcMainInvokeEvent, options: BridgeOptions): void {
  const result = checkSender(senderRequest(event, options), options.trustedOrigins);
  if (!result.ok) throw new Error(result.code);
}

export function registerBridge(options: BridgeOptions): () => void {
  const callHandler = async (
    event: IpcMainInvokeEvent,
    method: unknown,
    params: unknown,
  ): Promise<unknown> => {
    const policy = checkCallRequest(
      { ...senderRequest(event, options), method, params },
      options.trustedOrigins,
    );
    if (!policy.ok) throw new Error(policy.code);
    return options.service.request(policy.method, policy.params);
  };

  const getStatusHandler = async (event: IpcMainInvokeEvent) => {
    assertSender(event, options);
    return options.service.getStatus();
  };

  const restartServiceHandler = async (event: IpcMainInvokeEvent) => {
    assertSender(event, options);
    return options.service.restart();
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
  ipcMain.handle('workbench:get-status', getStatusHandler);
  ipcMain.handle('workbench:restart-service', restartServiceHandler);
  options.service.on('status', onStatus);
  options.service.on('rpc-event', onRpcEvent);

  return () => {
    ipcMain.removeHandler('workbench:call');
    ipcMain.removeHandler('workbench:get-status');
    ipcMain.removeHandler('workbench:restart-service');
    options.service.off('status', onStatus);
    options.service.off('rpc-event', onRpcEvent);
  };
}
