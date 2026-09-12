import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

// The workbench is built into the Python package so an installed copy ships a
// working local interface with no CDN, no font fetch, and no remote asset.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: resolve(__dirname, '../src/smartmoney_cub_harness/workbench/web'),
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
