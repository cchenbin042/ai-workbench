import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { _electron as electron, type ElectronApplication, type Page } from '@playwright/test';

export const repoRoot = path.resolve(__dirname, '..', '..', '..');
export const appRoot = path.join(repoRoot, 'apps', 'desktop');

function electronBinary(): string {
  const relative =
    process.platform === 'win32'
      ? path.join('node_modules', 'electron', 'dist', 'electron.exe')
      : process.platform === 'darwin'
        ? path.join('node_modules', 'electron', 'dist', 'Electron.app', 'Contents', 'MacOS', 'Electron')
        : path.join('node_modules', 'electron', 'dist', 'electron');
  const binary = path.join(appRoot, relative);
  if (!fs.existsSync(binary)) {
    throw new Error(`Electron binary not found: ${binary}`);
  }
  return binary;
}

export interface LaunchedWorkbench {
  app: ElectronApplication;
  page: Page;
  close: () => Promise<void>;
}

export async function launchWorkbench(): Promise<LaunchedWorkbench> {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'zhixu-e2e-'));
  const app = await electron.launch({
    executablePath: electronBinary(),
    args: [appRoot],
    cwd: appRoot,
    env: {
      ...process.env,
      WORKBENCH_SERVICE_MODE: 'python',
      WORKBENCH_REPO_ROOT: repoRoot,
      WORKBENCH_DATA_DIR: dataDir,
    },
  });
  const page = await app.firstWindow();
  await page.waitForLoadState('domcontentloaded');

  return {
    app,
    page,
    close: async () => {
      await app.close();
      fs.rmSync(dataDir, { recursive: true, force: true });
    },
  };
}
