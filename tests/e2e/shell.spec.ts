import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';

const repoRoot = path.resolve(__dirname, '..', '..');
const appRoot = path.join(repoRoot, 'apps', 'desktop');

let electronApp: ElectronApplication;
let page: Page;
let dataDir: string;

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

test.beforeAll(async () => {
  dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'zhixu-shell-'));
  electronApp = await electron.launch({
    executablePath: electronBinary(),
    args: [appRoot],
    cwd: appRoot,
    env: {
      ...process.env,
      WORKBENCH_SERVICE_MODE: 'python',
      WORKBENCH_REPO_ROOT: repoRoot,
      WORKBENCH_PYTHON: process.env.WORKBENCH_PYTHON ?? 'py',
      WORKBENCH_PYTHON_ARG: process.env.WORKBENCH_PYTHON_ARG ?? '-3.14',
      WORKBENCH_DATA_DIR: dataDir,
    },
  });
  page = await electronApp.firstWindow();
  await page.waitForLoadState('domcontentloaded');
});

test.afterAll(async () => {
  await electronApp?.close();
  if (dataDir) fs.rmSync(dataDir, { recursive: true, force: true });
});

test('@shell renders from app origin without Node APIs', async () => {
  expect(new URL(page.url()).protocol).toBe('app:');
  expect(await page.title()).toBe('知序 · 个人 AI 工作台');
  expect(await page.evaluate(() => typeof (window as Window & { require?: unknown }).require)).toBe('undefined');
  expect(await page.evaluate(() => typeof (window as Window & { process?: unknown }).process)).toBe('undefined');
  expect(await page.evaluate(() => typeof window.workbench.call)).toBe('function');
});

test('@shell serves the renderer with a restrictive CSP header', async () => {
  const csp = await page.evaluate(async () => {
    const response = await fetch(window.location.href);
    return response.headers.get('content-security-policy');
  });
  expect(csp).toContain("default-src 'self'");
  expect(csp).toContain("object-src 'none'");
});

test('@shell blocks popup windows and keeps the app origin', async () => {
  const opened = await page.evaluate(() => window.open('https://example.com') === null);
  expect(opened).toBe(true);
  expect(new URL(page.url()).protocol).toBe('app:');
});

test('@shell reaches the local service and rejects non-public methods', async () => {
  await expect(page.locator('[data-testid="service-status"]')).toHaveText('已连接');
  await expect(page.locator('[data-testid="service-protocol"]')).toHaveText('1');
  await expect(page.locator('[data-testid="service-schema"]')).toHaveText('0');

  const ping = await page.evaluate(() => window.workbench.call('system.ping', {}));
  expect((ping as { ok: boolean }).ok).toBe(true);

  const rejected = await page.evaluate(async () => {
    const call = window.workbench.call as unknown as (
      method: string,
      params?: Record<string, unknown>,
    ) => Promise<unknown>;
    try {
      await call('system.shutdown', {});
      return 'resolved';
    } catch (error) {
      return (error as Error).message;
    }
  });
  expect(rejected).toContain('METHOD_NOT_ALLOWED');
});

test('@shell contract type generation detects schema drift', async () => {
  const schemaPath = path.join(repoRoot, 'contracts', 'rpc.schema.json');
  if (!fs.existsSync(schemaPath)) {
    test.skip(true, 'contract schema has not been exported yet');
  }

  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'zhixu-contracts-'));
  const tempSchema = path.join(tempDir, 'rpc.schema.json');
  const tempOutput = path.join(tempDir, 'generated.ts');
  const generator = path.join(appRoot, 'scripts', 'generate-contract-types.mjs');
  fs.copyFileSync(schemaPath, tempSchema);

  const first = spawnSync(
    process.execPath,
    [generator, '--schema', tempSchema, '--output', tempOutput],
    { encoding: 'utf8' },
  );
  expect(first.status, first.stderr).toBe(0);

  const schema = JSON.parse(fs.readFileSync(tempSchema, 'utf8')) as Record<string, unknown>;
  const properties = (schema.properties as Record<string, unknown> | undefined) ?? {};
  schema.properties = { ...properties, contractDriftProbe: { type: 'string' } };
  fs.writeFileSync(tempSchema, JSON.stringify(schema, null, 2));

  const drift = spawnSync(
    process.execPath,
    [generator, '--schema', tempSchema, '--output', tempOutput, '--check'],
    { encoding: 'utf8' },
  );
  expect(drift.status).not.toBe(0);
  fs.rmSync(tempDir, { recursive: true, force: true });
});
