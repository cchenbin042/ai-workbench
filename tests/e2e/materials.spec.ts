import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { expect, test, type Page } from '@playwright/test';

import {
  launchWorkbench,
  type LaunchedWorkbench,
} from './support/workbench-app';

let workbench: LaunchedWorkbench;
let page: Page;
let materialsDir: string;

test.beforeAll(async () => {
  materialsDir = fs.mkdtempSync(path.join(os.tmpdir(), 'zhixu-materials-'));
  fs.writeFileSync(path.join(materialsDir, 'notes.md'), '# 学习计划\n第一行内容', 'utf-8');
  fs.mkdirSync(path.join(materialsDir, 'docs'));
  fs.writeFileSync(path.join(materialsDir, 'docs', 'Main.java'), 'class Main {}', 'utf-8');
  fs.writeFileSync(path.join(materialsDir, '.env'), 'SECRET=1', 'utf-8');
  fs.writeFileSync(path.join(materialsDir, '.env.example'), 'TEMPLATE=1', 'utf-8');
  fs.mkdirSync(path.join(materialsDir, 'node_modules'));
  fs.writeFileSync(path.join(materialsDir, 'node_modules', 'lib.js'), 'x', 'utf-8');
  fs.writeFileSync(path.join(materialsDir, 'app.exe'), Buffer.from([0x4d, 0x5a, 0x00, 0x01]));
  workbench = await launchWorkbench({
    env: { WORKBENCH_TEST_DIALOG_DIR: materialsDir },
  });
  page = workbench.page;
  page.on('framenavigated', (frame) => {
    if (frame === page.mainFrame()) console.log('[materials] main frame navigated:', frame.url());
  });
  page.on('pageerror', (error) => console.log('[materials] pageerror:', String(error)));
  page.on('crash', () => console.log('[materials] page crashed'));
  page.on('console', (message) => {
    if (message.type() === 'error') console.log('[materials] console error:', message.text());
  });
});

test.afterAll(async () => {
  await workbench?.close();
  fs.rmSync(materialsDir, { recursive: true, force: true });
});

test('@materials links a real directory, previews and imports selected files only', async () => {
  await page.getByRole('button', { name: '资料库', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1, name: '资料库' })).toBeFocused();

  await page.getByTestId('workspace-name').fill('开发空间');
  await page.getByTestId('create-workspace').click();
  await expect(page.getByTestId('workspace-item')).toHaveCount(1);

  // The dialog resolves to the test directory through the main-process grant.
  await page.getByTestId('link-directory').click();
  await expect(page.getByTestId('link-root')).toBeVisible();

  await page.getByTestId('open-listing').click();
  const rows = page.getByTestId('file-row');
  await expect(rows).toHaveCount(2);
  const listed = await rows.evaluateAll((nodes) =>
    nodes.map((node) => (node as HTMLElement).dataset.path),
  );
  expect(listed).toEqual(expect.arrayContaining(['docs/Main.java', 'notes.md']));
  for (const excluded of ['.env', '.env.example', 'node_modules/lib.js', 'app.exe']) {
    expect(listed).not.toContain(excluded);
  }

  await rows.filter({ hasText: 'notes.md' }).getByTestId('preview-file').click();
  await expect(page.getByTestId('preview-content')).toContainText('# 学习计划');

  await rows.filter({ hasText: 'notes.md' }).getByTestId('select-file').check();
  await rows.filter({ hasText: 'Main.java' }).getByTestId('select-file').check();
  await page.getByTestId('import-selected').click();
  await expect(page.getByTestId('material-item')).toHaveCount(2);
  await expect(page.getByTestId('material-name')).toHaveText(['notes.md', 'Main.java']);

  await page.getByTestId('check-freshness').click();
  await expect(page.getByTestId('freshness-status')).toHaveText([
    '与原文件一致',
    '与原文件一致',
  ]);
});

test('@materials unlink keeps original files and serves snapshots only', async () => {
  await page.getByTestId('unlink-link').click();
  await expect(page.getByTestId('link-item')).toContainText('已移除');
  await expect(page.getByTestId('listing-panel')).toContainText('没有有效的目录关联');

  expect(fs.existsSync(path.join(materialsDir, 'notes.md'))).toBe(true);
  expect(fs.readFileSync(path.join(materialsDir, 'notes.md'), 'utf-8')).toContain('第一行内容');
  expect(fs.existsSync(path.join(materialsDir, 'docs', 'Main.java'))).toBe(true);

  await expect(page.getByTestId('material-item')).toHaveCount(2);
  await page.getByTestId('check-freshness').click();
  await expect(page.getByTestId('freshness-status')).toHaveText([
    '无有效关联，仅剩快照',
    '无有效关联，仅剩快照',
  ]);
});

test('@materials isolates materials per workspace', async () => {
  await page.getByTestId('workspace-name').fill('办公空间');
  await page.getByTestId('create-workspace').click();
  await expect(page.getByTestId('workspace-item')).toHaveCount(2);
  await page.getByTestId('workspace-item').filter({ hasText: '办公空间' }).click();

  await expect(page.getByTestId('material-list')).toContainText('此空间还没有资料。');
  await expect(page.getByTestId('link-item')).toHaveCount(0);
  await expect(page.getByTestId('listing-panel')).toContainText('没有有效的目录关联');
});
