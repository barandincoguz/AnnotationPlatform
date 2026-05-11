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
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false },
      // NOTE: '/docs' (FastAPI Swagger UI) collided with the SPA route
      // '/docs/:docId'. Vite's proxy is a prefix match, so '/docs/foo'
      // was being proxied to backend instead of served as SPA. Removed.
      // Access Swagger UI directly at http://127.0.0.1:8000/docs during dev.
      '/openapi.json': 'http://127.0.0.1:8000',
      '/redoc': 'http://127.0.0.1:8000',
    },
  },
  build: {
    outDir: '../backend/static',
    emptyOutDir: true,
    sourcemap: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
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
