import { expect, test, type Page } from '@playwright/test';

import { launchWorkbench, type LaunchedWorkbench } from './support/workbench-app';

let workbench: LaunchedWorkbench;
let page: Page;

test.beforeAll(async () => {
  workbench = await launchWorkbench();
  page = workbench.page;
});

test.afterAll(async () => {
  await workbench?.close();
});

test('@settings shows the seeded DeepSeek config and reports a missing key', async () => {
  await page.getByRole('button', { name: '设置与工具', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1, name: '设置与工具' })).toBeFocused();

  await expect(page.getByTestId('provider-endpoint')).toHaveValue(
    'https://api.deepseek.com/chat/completions',
  );
  await expect(page.getByTestId('provider-model')).toHaveValue('deepseek-flash');
  await expect(page.getByTestId('provider-panel')).toContainText('密钥未配置');
  await expect(page.getByTestId('delete-secret')).toBeDisabled();

  // The connection test runs through the single execution slot and completes
  // with a structured outcome instead of failing the task.
  await page.getByTestId('test-connection').click();
  await expect(page.getByTestId('test-result')).toContainText('PROVIDER_NOT_CONFIGURED', {
    timeout: 30_000,
  });
  await expect(page.getByTestId('test-result')).toContainText('"ok": false');
});
