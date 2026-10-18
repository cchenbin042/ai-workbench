import fs from 'node:fs';
import path from 'node:path';

import { MakerSquirrel } from '@electron-forge/maker-squirrel';
import { MakerZIP } from '@electron-forge/maker-zip';
import { VitePlugin } from '@electron-forge/plugin-vite';
import type { ForgeConfig } from '@electron-forge/shared-types';

const projectRoot = process.cwd();
const bundledService = path.resolve(projectRoot, '../../services/workbench/dist/workbench-service');

const config: ForgeConfig = {
  packagerConfig: {
    name: 'ZhixuWorkbench',
    asar: true,
    extraResource: fs.existsSync(bundledService) ? [bundledService] : [],
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
