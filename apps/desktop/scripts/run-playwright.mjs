#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import path from 'node:path';
import process from 'node:process';

const require = createRequire(import.meta.url);
const projectDir = path.resolve(import.meta.dirname, '..');
const configPath = path.resolve(projectDir, '..', '..', 'tests', 'e2e', 'playwright.config.ts');

const result = spawnSync(
  process.execPath,
  [require.resolve('@playwright/test/cli'), 'test', '--config', configPath, ...process.argv.slice(2)],
  {
    cwd: projectDir,
    stdio: 'inherit',
    env: {
      ...process.env,
      NODE_PATH: path.join(projectDir, 'node_modules'),
    },
  },
);

process.exit(result.status ?? 1);
