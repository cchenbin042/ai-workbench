import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: __dirname,
  timeout: 60_000,
  expect: {
    timeout: 20_000,
  },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    trace: 'retain-on-failure',
  },
});
