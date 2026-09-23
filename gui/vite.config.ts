import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';
import { fileURLToPath } from 'url';

// The workbench is built into the Python package so an installed copy ships a
// working local interface with no CDN, no font fetch, and no remote asset.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: resolve(fileURLToPath(new URL('.', import.meta.url)), '../src/smartmoney_cub_harness/workbench/web'),
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8787',
        changeOrigin: false,
      },
    },
  },
});
