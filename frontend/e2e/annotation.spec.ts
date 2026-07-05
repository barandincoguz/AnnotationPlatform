import { test, expect } from '@playwright/test'
import { E2E_DOC_IDS, loginAs } from './helpers'

test.describe('Annotation flow', () => {
  test('two users serialize editing and preserve the version chain', async ({ browser }) => {
    const aliceContext = await browser.newContext()
    const bobContext = await browser.newContext()
    const alice = await aliceContext.newPage()
    const bob = await bobContext.newPage()

    try {
      await loginAs(alice, 'alice')
      await loginAs(bob, 'bob')

      await alice.goto(`/docs/${E2E_DOC_IDS.concurrency}`)
      await expect(alice.getByRole('button', { name: 'Kontrole Gönder' })).toBeVisible()

      await bob.goto(`/docs/${E2E_DOC_IDS.concurrency}`)
      await expect(bob.getByRole('dialog', { name: /alice düzenliyor/i })).toBeVisible()

      const [aliceSaveResponse, aliceReleaseResponse] = await Promise.all([
        alice.waitForResponse((response) =>
          response.url().endsWith('/api/annotations')
          && response.request().method() === 'POST',
        ),
        alice.waitForResponse((response) =>
          response.url().endsWith(`/api/locks/${E2E_DOC_IDS.concurrency}/release`)
          && response.request().method() === 'POST',
        ),
        alice.getByRole('button', { name: 'Kontrole Gönder' }).click(),
      ])
      expect(aliceSaveResponse.ok()).toBeTruthy()
      expect(aliceReleaseResponse.ok()).toBeTruthy()

      await bob.getByRole('button', { name: 'Listeye dön' }).click()
      await expect(bob).toHaveURL(/\/$/)
      await bob.goto(`/docs/${E2E_DOC_IDS.concurrency}`)
      await expect(bob.getByRole('button', { name: 'Kontrole Gönder' })).toBeVisible()

      await bob.getByRole('button', { name: 'Yeni Referans' }).click()
      await bob.getByRole('textbox', { name: 'Kanun No' }).fill('193')
      await bob.getByRole('textbox', { name: 'Madde' }).fill('37')
      await bob.getByRole('textbox', { name: 'Metinden Alıntı' }).fill(
        '193 sayili Gelir Vergisi Kanununun 37. maddesi',
      )
      const [bobSaveResponse, bobReleaseResponse] = await Promise.all([
        bob.waitForResponse((response) =>
          response.url().endsWith('/api/annotations')
          && response.request().method() === 'POST',
        ),
        bob.waitForResponse((response) =>
          response.url().endsWith(`/api/locks/${E2E_DOC_IDS.concurrency}/release`)
          && response.request().method() === 'POST',
        ),
        bob.getByRole('button', { name: 'Kontrole Gönder' }).click(),
      ])
      expect(bobSaveResponse.ok()).toBeTruthy()
      expect(bobReleaseResponse.ok()).toBeTruthy()

      const response = await bobContext.request.get(
        `/api/documents/${E2E_DOC_IDS.concurrency}/annotation`,
      )
      expect(response.ok()).toBeTruthy()
      const body = await response.json() as {
        annotation: {
          references: Array<{ kanun_no: string; madde: string }>
          edit_count: number
          unique_users_count: number
        }
        chain: Array<{ username: string; action: string }>
      }

      expect(body.annotation.references).toMatchObject([
        { kanun_no: '193', madde: '37' },
      ])
      expect(body.annotation.edit_count).toBe(2)
      expect(body.annotation.unique_users_count).toBe(2)
      expect(body.chain.map((version) => version.username)).toEqual([
        'alice',
        'bob',
      ])
      expect(body.chain.map((version) => version.action)).toEqual([
        'create',
        'edit',
      ])
    } finally {
      await Promise.allSettled([
        alice.close({ runBeforeUnload: false }),
        bob.close({ runBeforeUnload: false }),
      ])
      await Promise.allSettled([
        aliceContext.close(),
        bobContext.close(),
      ])
    }
  })

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
    // The source references are intentionally collapsed by default.
    // Opening them must reveal the destructive reliability warning.
    await page.getByRole('button', { name: /kaynak veri referansları/i }).click()
    const warning = page.getByTestId('refs-source-warning')
    await expect(warning).toBeVisible({ timeout: 10_000 })
    await expect(warning).toContainText(/güvensiz/i)
  })

  test('tabs switch the doc list under their semantic identity', async ({ page }) => {
    await loginAs(page, 'alice')
    await expect(page.getByRole('tab', { name: /yeni/i })).toHaveAttribute(
      'data-state',
      'active',
    )
    const reviewTab = page.getByRole('tab', { name: /kontrol gerekiyor/i })
    await reviewTab.click()
    await expect(reviewTab).toHaveAttribute('data-state', 'active')
  })

  test('sort menu is hidden from end users by default (phase 6 contract)', async ({ page }) => {
    // Phase 6 cross-team coordination contract: every annotator on
    // this deploy AND on the partner-team deploy must see the same
    // document_id DESC feed sequence. The SortMenu is therefore not
    // rendered to end users — exposing a user-controlled sort would
    // silently break the contract.
    await loginAs(page, 'alice')
    // Trigger must be absent in the DOM, not just hidden.
    await expect(page.getByRole('button', { name: /sıralama/i })).toHaveCount(0)
  })

  test('sort menu surfaces every key + document_id when dev flag is set', async ({ page }) => {
    // Developer escape hatch: localStorage.a11n.dev_sort=1 re-enables
    // the menu without a code change. This test exercises that path
    // end-to-end and asserts the Phase 6 canonical key (Özelge ID =
    // document_id) appears alongside the legacy keys.
    await loginAs(page, 'alice')
    // Set the flag against the SPA origin, then reload so the
    // SortMenu re-evaluates isDevSortEnabled() during mount.
    await page.evaluate(() => window.localStorage.setItem('a11n.dev_sort', '1'))
    await page.reload()
    await page.getByRole('button', { name: /sıralama/i }).click()
    await expect(page.getByRole('menuitem', { name: 'Özelge ID' })).toBeVisible()
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
