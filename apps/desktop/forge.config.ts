import fs from 'node:fs';
import path from 'node:path';

import { MakerSquirrel } from '@electron-forge/maker-squirrel';
import { MakerZIP } from '@electron-forge/maker-zip';
import { VitePlugin } from '@electron-forge/plugin-vite';
import type { ForgeConfig } from '@electron-forge/shared-types';

const projectRoot = process.cwd();
const bundledService = path.resolve(projectRoot, '../../services/workbench/dist/workbench-service');

// Pinned sha256 of the Electron 44.9.0 win32-x64 zip, matching the official
// SHASUMS256.txt entry. Supplying it keeps packaging verifiable when the
// checksum file itself cannot be fetched on a flaky or offline network.
const electronZipChecksums: Record<string, string> = {
  'electron-v44.9.0-win32-x64.zip': '88e08039d0ef359bab9f674e8051fa103bd8628ea7c5a5e1daaa610a8a0c6931',
};

const config: ForgeConfig = {
  packagerConfig: {
    name: 'ZhixuWorkbench',
    asar: true,
    extraResource: fs.existsSync(bundledService) ? [bundledService] : [],
    download: { checksums: electronZipChecksums } as never,
  },
  rebuildConfig: {},
  makers: [
    new MakerSquirrel({ name: 'zhixu_workbench' }),
    new MakerZIP({}, ['win32']),
  ],
  plugins: [
    new VitePlugin({
      build: [
        {
          entry: 'src/main/index.ts',
          config: 'vite.main.config.ts',
          target: 'main',
        },
        {
          entry: 'src/preload/index.ts',
          config: 'vite.preload.config.ts',
          target: 'preload',
        },
      ],
      renderer: [
        {
          name: 'main_window',
          config: 'vite.renderer.config.ts',
        },
      ],
    }),
  ],
};

export default config;
