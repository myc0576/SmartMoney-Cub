import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { viteSingleFile } from 'vite-plugin-singlefile';
import { resolve } from 'path';

export default defineConfig({
  plugins: [react(), viteSingleFile()],
  build: {
    outDir: resolve(__dirname, '../src/smartmoney_cub_harness/dashboard/templates'),
    emptyOutDir: false,
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: false,
      },
    },
  },
});
