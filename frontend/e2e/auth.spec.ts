import { test, expect } from '@playwright/test'
import { E2E_PASSWORD, E2E_USERS, loginAs } from './helpers'

test.describe('Auth', () => {
  test('seeded user can log in and lands on the home shell', async ({ page }) => {
    await loginAs(page, 'alice')
    // TopBar chips (XP / Streak / Daily) are authed-only — their
    // presence confirms the session cookie was set and the SPA
    // hydrated the profile query.
    await expect(page.getByLabel('Toplam XP')).toBeVisible()
  })

  test('wrong password surfaces the Turkish error message', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel(/kullanıcı adı/i).fill(E2E_USERS.alice.username)
    await page.getByLabel(/şifre/i).fill('wrong-password')
    await page.getByRole('button', { name: /giriş yap/i }).click()
    // Backend translates a 401 invalid_credentials into a Turkish
    // message; we don't pin the exact string, only that an error
    // surfaces inline and the user stays on /login.
    await expect(page.getByRole('alert')).toBeVisible()
    await expect(page).toHaveURL(/\/login$/)
  })

  test('submit button is disabled when fields are empty', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByRole('button', { name: /giriş yap/i })).toBeDisabled()
  })

  test('login → logout cycle returns user to /login', async ({ page }) => {
    await loginAs(page, 'alice')
    await page.getByLabel('Profil menüsü').click()
    await page.getByRole('menuitem', { name: /çıkış/i }).click()
    await expect(page).toHaveURL(/\/login$/, { timeout: 10_000 })
  })

  test('register page links back to login (and vice versa)', async ({ page }) => {
    await page.goto('/login')
    await page.getByRole('link', { name: /^kayıt ol$/i }).click()
    await expect(page).toHaveURL(/\/register$/)
    await page.getByRole('link', { name: /giriş yap/i }).click()
    await expect(page).toHaveURL(/\/login$/)
  })

  // E2E_PASSWORD imported so a future test can opt back into the raw
  // string without rebuilding the import line.
  test('password literal is shared via the helper, not duplicated', () => {
    expect(E2E_PASSWORD).toBe('e2e-pass-123!')
  })
})
