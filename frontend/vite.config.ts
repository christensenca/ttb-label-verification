/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // E2E_API_URL lets Playwright runs point the dev server at the stub
      // backend on a non-default port (see scripts/serve_with_stub_extractor.py).
      '/api': process.env.E2E_API_URL ?? 'http://localhost:8000',
      '/healthz': process.env.E2E_API_URL ?? 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: true,
    exclude: ['**/node_modules/**', '**/dist/**', 'tests/e2e/**'],
  },
})
