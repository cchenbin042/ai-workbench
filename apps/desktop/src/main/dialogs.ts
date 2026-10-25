import { app, dialog, ipcMain, type BrowserWindow, type IpcMainInvokeEvent } from 'electron';

import { checkSender, type SenderRequest } from '../shared/ipc-policy';
import type { WorkbenchService } from './service-process';

export interface DialogOptions {
  window: BrowserWindow;
  service: WorkbenchService;
  trustedOrigins: string[];
}

export interface RegisteredGrant {
  grantId: string;
  kind: 'directory' | 'files';
  expiresAt: string;
  root: string | null;
  files: string[];
}

function senderRequest(event: IpcMainInvokeEvent, options: DialogOptions): SenderRequest {
  return {
    senderIsMainWindow: event.sender === options.window.webContents,
    frameIsMainFrame: event.senderFrame === options.window.webContents.mainFrame,
    frameUrl: event.senderFrame?.url ?? null,
  };
}

function assertSender(event: IpcMainInvokeEvent, options: DialogOptions): void {
  const result = checkSender(senderRequest(event, options), options.trustedOrigins);
  if (!result.ok) throw new Error(result.code);
}

async function registerGrant(
  service: WorkbenchService,
  params: Record<string, unknown>,
): Promise<RegisteredGrant> {
  const grant = await service.request<Record<string, unknown>>('internal.registerGrant', params);
  return {
    grantId: String(grant.grant_id),
    kind: grant.kind as 'directory' | 'files',
    expiresAt: String(grant.expires_at),
    root: grant.root === null ? null : String(grant.root),
    files: Array.isArray(grant.files) ? grant.files.map(String) : [],
  };
}

// Test hook: e2e runs cannot drive a native dialog, so an explicit environment
// directory replaces it. Never available in packaged builds.
function testDialogDirectory(): string | null {
  if (app.isPackaged) return null;
  const candidate = process.env.WORKBENCH_TEST_DIALOG_DIR;
  return candidate && candidate.trim() ? candidate : null;
}

export function registerDialogs(options: DialogOptions): () => void {
  const chooseDirectoryHandler = async (event: IpcMainInvokeEvent): Promise<RegisteredGrant | null> => {
    assertSender(event, options);
    const testDirectory = testDialogDirectory();
    const selected = testDirectory
      ? { canceled: false, filePaths: [testDirectory] }
      : await dialog.showOpenDialog(options.window, {
          title: '选择要关联的项目目录',
          properties: ['openDirectory', 'dontAddToRecent'],
        });
    if (selected.canceled || selected.filePaths.length !== 1) return null;
    return registerGrant(options.service, { kind: 'directory', path: selected.filePaths[0] });
  };

  const chooseFilesHandler = async (event: IpcMainInvokeEvent): Promise<RegisteredGrant | null> => {
    assertSender(event, options);
    const selected = await dialog.showOpenDialog(options.window, {
      title: '选择要导入的文本资料',
      properties: ['openFile', 'multiSelections', 'dontAddToRecent'],
    });
    if (selected.canceled || selected.filePaths.length === 0) return null;
    return registerGrant(options.service, { kind: 'files', paths: selected.filePaths });
  };

  ipcMain.handle('workbench:choose-directory', chooseDirectoryHandler);
  ipcMain.handle('workbench:choose-files', chooseFilesHandler);
  return () => {
    ipcMain.removeHandler('workbench:choose-directory');
    ipcMain.removeHandler('workbench:choose-files');
  };
}
