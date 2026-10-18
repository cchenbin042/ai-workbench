import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test, type Page } from '@playwright/test';

import {
  appRoot,
  launchWorkbench,
  repoRoot,
  type LaunchedWorkbench,
} from './support/workbench-app';

let workbench: LaunchedWorkbench;
let page: Page;

test.beforeAll(async () => {
  workbench = await launchWorkbench();
  page = workbench.page;
});

test.afterAll(async () => {
  await workbench?.close();
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
  expect(csp).toContain("script-src 'self'");
  expect(csp).not.toContain("script-src 'self' 'unsafe-inline'");
  expect(csp).toContain("object-src 'none'");
  expect(csp).toContain("frame-src 'none'");
});

test('@shell blocks popup windows and external navigation', async () => {
  const before = workbench.app.windows().length;
  const opened = await page.evaluate(() => window.open('https://example.com') === null);
  expect(opened).toBe(true);
  expect(workbench.app.windows().length).toBe(before);

  await page.evaluate(() => {
    window.location.href = 'https://example.com/';
  });
  await page.waitForTimeout(300);
  expect(new URL(page.url()).protocol).toBe('app:');

  await page.reload();
  await page.waitForLoadState('domcontentloaded');
});

test('@shell rejects path traversal on the app protocol', async () => {
  const result = await page.evaluate(async () => {
    try {
      const response = await fetch('app://workbench/%2E%2E/%2E%2E/package.json');
      return { status: response.status, text: await response.text() };
    } catch {
      return { status: 0, text: '' };
    }
  });
  expect([0, 403, 404]).toContain(result.status);
  expect(result.text).not.toContain('zhixu-workbench-desktop');
});

test('@shell reaches the local service and rejects non-public methods', async () => {
  await expect(page.locator('[data-testid="service-status"]')).toHaveText('已连接');
  await expect(page.locator('[data-testid="service-protocol"]')).toHaveText('1');
  await expect(page.locator('[data-testid="service-schema"]')).toHaveText('0');

  const status = await page.evaluate(() => window.workbench.getStatus());
  expect(status.state).toBe('connected');
  expect(status.protocolVersion).toBe(1);
  expect(status.schemaVersion).toBe(0);
  expect(await page.evaluate(() => typeof window.workbench.restartService)).toBe('function');

  const ping = await page.evaluate(() => window.workbench.call('system.ping', {}));
  expect((ping as { ok: boolean }).ok).toBe(true);

  for (const method of ['system.shutdown', 'system.initialize', 'materials.list']) {
    const rejected = await page.evaluate(async (blockedMethod) => {
      const call = window.workbench.call as unknown as (
        name: string,
        params?: Record<string, unknown>,
      ) => Promise<unknown>;
      try {
        await call(blockedMethod, {});
        return 'resolved';
      } catch (error) {
        return (error as Error).message;
      }
    }, method);
    expect(rejected).toContain('METHOD_NOT_ALLOWED');
  }
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
