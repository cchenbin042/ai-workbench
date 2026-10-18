import path from 'node:path';

import { defineConfig } from 'vite';

export default defineConfig({
  build: {
    lib: {
      entry: 'src/main/index.ts',
      fileName: () => 'main.cjs',
      formats: ['cjs'],
    },
  },
  resolve: {
    alias: {
      '@shared': path.resolve(__dirname, 'src/shared'),
      '@contracts': path.resolve(__dirname, '../../contracts'),
    },
  },
});
