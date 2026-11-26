/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

const dataDir = fileURLToPath(new URL('../data', import.meta.url));

export default defineConfig({
  plugins: [react()],
  base: './',
  resolve: { alias: { '@data': dataDir } },
  server: { fs: { allow: ['..'] } },
  worker: { format: 'es' },
  build: { chunkSizeWarningLimit: 1500 },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
});
