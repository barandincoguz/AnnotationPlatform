/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, 'src') },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // VITE_PROXY_TARGET lets the e2e harness point the dev server at
      // an isolated backend (e.g. http://127.0.0.1:8001) without touching
      // production data. Default keeps the standard dev mapping.
      '/api': {
        target: process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
      // NOTE: '/docs' (FastAPI Swagger UI) collided with the SPA route
      // '/docs/:docId'. Vite's proxy is a prefix match, so '/docs/foo'
      // was being proxied to backend instead of served as SPA. Removed.
      // Access Swagger UI directly at http://127.0.0.1:8000/docs during dev.
      '/openapi.json': process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8000',
      '/redoc': process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8000',
    },
  },
  build: {
    outDir: '../backend/static',
    emptyOutDir: true,
    sourcemap: true,
  },
  test: {
    environment: 'happy-dom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    // Vitest's default include matches *.spec.ts — but our e2e specs
    // live in ./e2e and are Playwright tests, not Vitest. Without this
    // exclusion `npm test` tries to load them and crashes on the
    // @playwright/test imports.
    exclude: ['e2e/**', 'node_modules/**', 'dist/**', 'playwright-report/**'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/test/**',
        'src/**/*.test.{ts,tsx}',
        'src/api/types.ts',
        // Bootstrap / type declarations — not unit-testable
        'src/main.tsx',
        'src/vite-env.d.ts',
        // env reader — exercised at module load by main.tsx in dev/prod
        'src/lib/env.ts',
        // STUB routes — 16b-e content; 16a only wires routing
        'src/routes/Annotate.tsx',
        'src/routes/Profile.tsx',
        'src/routes/Help.tsx',
        'src/routes/NotFound.tsx',
        'src/routes/admin/AdminLayout.tsx',
        // shadcn primitives installed for later use — vendor-style code
        'src/components/ui/form.tsx',
        'src/components/ui/sonner.tsx',
      ],
      thresholds: {
        statements: 80,
        branches: 80,
        functions: 80,
        lines: 80,
      },
    },
  },
})
