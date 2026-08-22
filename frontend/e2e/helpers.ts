import { type Page, expect } from '@playwright/test'

/**
 * Credentials baked into the e2e seed (backend/cli.py::cmd_seed_e2e).
 * Plain password literals are fine here — the seed only runs against
 * an isolated /tmp/anotasyon-e2e-* directory; the seed command has no force
 * bypass and refuses both production mode and every non-temporary path.
 */
export const E2E_PASSWORD = 'e2e-pass-123!'
export const E2E_USERS = {
  alice: { username: 'alice', password: E2E_PASSWORD },
  bob: { username: 'bob', password: E2E_PASSWORD },
  admin: { username: 'admin', password: E2E_PASSWORD },
}

export const E2E_DOC_IDS = {
  alpha: 'e2e-doc-alpha',
  bravo: 'e2e-doc-bravo',
  charlie: 'e2e-doc-charlie',
  concurrency: 'e2e-doc-concurrency',
}

/**
 * Log a seeded user in via the public /login route, then wait for the
 * SPA to land on the authed home screen.
 */
export async function loginAs(page: Page, who: keyof typeof E2E_USERS) {
  const { username, password } = E2E_USERS[who]
  await page.goto('/login')
  await page.getByLabel(/kullanıcı adı/i).fill(username)
  await page.getByLabel(/şifre/i).fill(password)
  await page.getByRole('button', { name: /giriş yap/i }).click()
  // The brand mark is the simplest "we're past the login screen"
  // signal — it sits in the topbar of every authed route.
  await expect(page.getByRole('link', { name: /anotasyon ana sayfa/i })).toBeVisible({
    timeout: 10_000,
  })
}
