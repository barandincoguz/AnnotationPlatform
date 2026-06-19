import { defineConfig, devices } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const REPO_ROOT = path.resolve(__dirname, '..')
const E2E_DATA_DIR = '/tmp/anotasyon-e2e-data'
const E2E_BACKEND_PORT = 8001
const E2E_FRONTEND_PORT = 5174
const PROXY_TARGET = `http://127.0.0.1:${E2E_BACKEND_PORT}`

/**
 * Playwright config for the annotation platform.
 *
 * Lifecycle: a single Playwright run owns its own isolated backend
 * + frontend, both on dedicated ports so they never collide with the
 * developer's dev servers (`npm run dev` keeps 5173 + 8000).
 *
 * - Backend: `DATA_DIR=/tmp/anotasyon-e2e-data uvicorn backend.main:app
 *   --port 8001`. The seed script reset+rebuilds that DB before the
 *   server boots, so every full run starts from the same fixtures
 *   (alice/bob/admin + 4 sample docs + invite "E2E-CODE").
 * - Frontend: `VITE_PROXY_TARGET=http://127.0.0.1:8001 vite --port 5174`.
 *   The proxy override is read by frontend/vite.config.ts so the SPA
 *   talks to the isolated backend.
 *
 * `reuseExistingServer: true` lets quick iterations (e.g. `playwright
 * test --ui` while the servers are already up) skip the boot
 * sequence. Set the SEED env var to force a fresh seed regardless.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? 'github' : 'list',
  timeout: 30_000,
  expect: { timeout: 5_000 },

  use: {
    baseURL: `http://127.0.0.1:${E2E_FRONTEND_PORT}`,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: [
    {
      // Boot order: seed → uvicorn. `&&` so any seed failure aborts
      // the whole run rather than serving a stale DB.
      command:
        `DATA_DIR=${E2E_DATA_DIR} ${REPO_ROOT}/.venv/bin/python -m backend.cli seed-e2e --reset && ` +
        `DATA_DIR=${E2E_DATA_DIR} SESSION_SECRET=e2e-secret-DO-NOT-USE-IN-PROD ` +
        `${REPO_ROOT}/.venv/bin/python -m uvicorn backend.main:app ` +
        `--host 127.0.0.1 --port ${E2E_BACKEND_PORT} --log-level info`,
      // /openapi.json returns 200 once FastAPI is up, so the health
      // probe finishes the moment uvicorn finishes binding. We can't
      // use /api/auth/me because it intentionally returns 401 when
      // unauthenticated, which Playwright's webServer treats as
      // "not ready".
      url: `http://127.0.0.1:${E2E_BACKEND_PORT}/openapi.json`,
      ignoreHTTPSErrors: true,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      stdout: 'pipe',
      stderr: 'pipe',
      cwd: REPO_ROOT,
    },
    {
      command:
        `VITE_PROXY_TARGET=${PROXY_TARGET} ` +
        `npm run dev -- --host 127.0.0.1 --port ${E2E_FRONTEND_PORT} --strictPort`,
      url: `http://127.0.0.1:${E2E_FRONTEND_PORT}`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      stdout: 'pipe',
      stderr: 'pipe',
      cwd: __dirname,
    },
  ],
})
