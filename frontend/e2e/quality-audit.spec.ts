import { expect, test } from '@playwright/test'

import { E2E_DOC_IDS, loginAs } from './helpers'

const HUMAN_QUOTE = 'Kira gelirinin vergilendirilmesi hakkinda ozelge talebi.'

test.describe('Pre-submit quality audit', () => {
  test('RED audit → accept the model suggestion → complete', async ({ page }) => {
    await loginAs(page, 'alice')
    await page.goto(`/docs/${E2E_DOC_IDS.alpha}`)

    // Enter the human's single reference: GVK 37 with the model's own quote,
    // so the only disagreement left is the model's extra VUK 114.
    await page.getByRole('button', { name: 'Yeni Referans' }).click()
    await page.getByLabel(/kanun no/i).first().fill('193')
    await page.getByLabel(/^madde/i).first().fill('37')
    await page.getByLabel(/metinden alıntı/i).first().fill(HUMAN_QUOTE)

    const [auditResponse] = await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().includes(`/api/annotations/${E2E_DOC_IDS.alpha}/pre-audit`)
          && response.request().method() === 'POST',
      ),
      page.getByRole('button', { name: /^tamamlandı$/i }).click(),
    ])
    expect(auditResponse.ok()).toBeTruthy()
    expect((await auditResponse.json()).bucket).toBe('RED')

    // The audit panel takes over the right pane; the document stays visible.
    await expect(page.getByText('Model Karşılaştırma & Kalite Denetimi')).toBeVisible()
    await expect(page.getByText(/Model yanılıyor olabilir/)).toBeVisible()
    await expect(page.getByText('Model buldu, sizde yok')).toBeVisible()

    // The claimed quote is marked in the document body.
    await expect(
      page.locator('mark', { hasText: 'Konuyla ilgili aciklamalar' }),
    ).toBeVisible()

    await page.getByRole('button', { name: 'Model Önerisini Listeme Ekle' }).click()
    await expect(page.getByRole('button', { name: 'Eklendi' })).toBeDisabled()

    const [completeResponse] = await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().includes(`/api/annotations/${E2E_DOC_IDS.alpha}/complete`)
          && response.request().method() === 'POST',
      ),
      page.getByRole('button', { name: 'Tamamla', exact: true }).click(),
    ])
    expect(completeResponse.ok()).toBeTruthy()
  })

  test('override keeps the human labels and still completes', async ({ page }) => {
    await loginAs(page, 'bob')
    await page.goto(`/docs/${E2E_DOC_IDS.bravo}`)

    await page.getByRole('button', { name: 'Yeni Referans' }).click()
    await page.getByLabel(/kanun no/i).first().fill('193')
    await page.getByLabel(/^madde/i).first().fill('37')
    await page.getByLabel(/metinden alıntı/i).first().fill(HUMAN_QUOTE)

    await page.getByRole('button', { name: /^tamamlandı$/i }).click()
    await expect(page.getByText('Model Karşılaştırma & Kalite Denetimi')).toBeVisible()

    const [completeResponse] = await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().includes(`/api/annotations/${E2E_DOC_IDS.bravo}/complete`)
          && response.request().method() === 'POST',
      ),
      page.getByRole('button', { name: 'Benim Etiketim Doğru, Yine de Tamamla' }).click(),
    ])
    expect(completeResponse.ok()).toBeTruthy()
  })
})
