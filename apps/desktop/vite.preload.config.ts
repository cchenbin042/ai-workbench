import path from 'node:path';

import { defineConfig } from 'vite';

export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        entryFileNames: 'preload.cjs',
      },
    },
  },
  resolve: {
    alias: {
      '@shared': path.resolve(__dirname, 'src/shared'),
      '@contracts': path.resolve(__dirname, '../../contracts'),
    },
  },
});
