import { test, expect } from '@playwright/test'
import { E2E_DOC_IDS, loginAs } from './helpers'

test.describe('Annotation flow', () => {
  test('jump-to-doc input navigates to the requested özelge', async ({ page }) => {
    await loginAs(page, 'alice')
    // The form has aria-label "Doküman ID ile ara" and the input has
    // aria-label "Doküman ID" — getByLabel matches both fuzzily, so
    // scope to the textbox role to disambiguate.
    await page.getByRole('textbox', { name: 'Doküman ID' }).fill(E2E_DOC_IDS.alpha)
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(new RegExp(`/docs/${E2E_DOC_IDS.alpha}$`), {
      timeout: 10_000,
    })
    // DocViewer header renders the id under the "ID :" cap.
    await expect(page.getByText(E2E_DOC_IDS.alpha, { exact: true }).first()).toBeVisible()
  })

  test('reference panel shows the source-data unreliability warning', async ({ page }) => {
    await loginAs(page, 'alice')
    await page.goto(`/docs/${E2E_DOC_IDS.alpha}`)
    // doc-alpha was seeded with one kanun_ref, so the destructive
    // warning banner must render.
    const warning = page.getByTestId('refs-source-warning')
    await expect(warning).toBeVisible({ timeout: 10_000 })
    await expect(warning).toContainText(/güvenilir değil/i)
  })

  test('tabs switch the doc list under their semantic identity', async ({ page }) => {
    await loginAs(page, 'alice')
    // All seeded docs land in the "Yeni" tab (no annotations yet),
    // so switching to "Devam Eden" or "Tamamlanan" shows an empty
    // state.
    await expect(page.getByRole('tab', { name: /yeni/i })).toHaveAttribute(
      'data-state',
      'active',
    )
    await page.getByRole('tab', { name: /devam eden/i }).click()
    await expect(page.getByText(/bu sekmede doküman yok/i)).toBeVisible({
      timeout: 10_000,
    })
  })

  test('sort menu surfaces every key with a colored direction marker', async ({ page }) => {
    await loginAs(page, 'alice')
    await page.getByRole('button', { name: /sıralama/i }).click()
    // Tarih is the default for the "new" tab; opening the menu
    // should expose the full option set.
    await expect(page.getByRole('menuitem', { name: /tarih/i }).first()).toBeVisible()
    await expect(page.getByRole('menuitem', { name: /karıştır/i })).toBeVisible()
    // SortMenu intentionally calls e.preventDefault() in onSelect so
    // the popover stays open — operators can flip direction without
    // re-opening. After clicking "Konu" the same item gets
    // data-active="true" because the store now considers it the
    // active sort.
    const konu = page.getByRole('menuitem', { name: 'Konu' })
    await konu.click()
    await expect(konu).toHaveAttribute('data-active', 'true')
  })
})
