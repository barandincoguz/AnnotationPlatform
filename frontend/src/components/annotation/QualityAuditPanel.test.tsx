import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { QualityAuditPanel } from './QualityAuditPanel'
import { discrepancyKey } from './audit-utils'
import type { AuditDiscrepancy, PreAuditResult } from '@/api/queries/annotations'

const MODEL_ONLY: AuditDiscrepancy = {
  kind: 'model_only',
  kanun_no: '193',
  kanun_ad: 'Gelir Vergisi Kanunu',
  madde: '94',
  model_reference: {
    kanun_no: '193', kanun_ad: 'Gelir Vergisi Kanunu', madde: '94',
    fikra: '1', bent: 'b', source_text: 'tevkifat esaslarini belirler',
  },
  human_reference: null,
  field_diffs: [],
  match_mode: 'normalized_exact',
}

const HUMAN_ONLY: AuditDiscrepancy = {
  kind: 'human_only',
  kanun_no: '3065',
  kanun_ad: 'Katma Değer Vergisi Kanunu',
  madde: '17',
  model_reference: null,
  human_reference: {
    kanun_no: '3065', kanun_ad: 'Katma Değer Vergisi Kanunu', madde: '17',
    fikra: '', bent: '', source_text: 'istisna hukmu',
  },
  field_diffs: [],
  match_mode: null,
}

const DETAIL: AuditDiscrepancy = {
  kind: 'detail_mismatch',
  kanun_no: '213',
  kanun_ad: 'Vergi Usul Kanunu',
  madde: '114',
  model_reference: {
    kanun_no: '213', kanun_ad: 'Vergi Usul Kanunu', madde: '114',
    fikra: '2', bent: '', source_text: 'zamanasimi',
  },
  human_reference: {
    kanun_no: '213', kanun_ad: 'Vergi Usul Kanunu', madde: '114',
    fikra: '1', bent: '', source_text: 'zamanasimi',
  },
  field_diffs: ['fikra'],
  match_mode: 'loose_alphanumeric',
}

function makeResult(overrides: Partial<PreAuditResult> = {}): PreAuditResult {
  return {
    audit_status: 'ready',
    reason: null,
    bucket: 'RED',
    reasons: ['extra_or_different_core_reference'],
    similarity: 0.5,
    prediction_fingerprint: 'fp-1',
    model_generation: 'G0',
    discrepancies: [MODEL_ONLY, HUMAN_ONLY, DETAIL],
    ...overrides,
  }
}

function renderPanel(props: Partial<React.ComponentProps<typeof QualityAuditPanel>> = {}) {
  const handlers = {
    onAccept: vi.fn(),
    onHover: vi.fn(),
    onComplete: vi.fn(),
    onOverride: vi.fn(),
    onBackToEdit: vi.fn(),
  }
  render(
    <QualityAuditPanel
      result={makeResult()}
      acceptedKeys={new Set()}
      isCompleting={false}
      canEdit={true}
      {...handlers}
      {...props}
    />,
  )
  return handlers
}

describe('QualityAuditPanel', () => {
  it('always shows the cognitive safeguard warning', () => {
    renderPanel()
    expect(screen.getByText('Model Karşılaştırma & Kalite Denetimi')).toBeInTheDocument()
    expect(
      screen.getByText(/Model yanılıyor olabilir/),
    ).toBeInTheDocument()
    expect(screen.getByText('Kanun veya madde listesi uyuşmuyor')).toBeInTheDocument()
  })

  it('offers an add button only for references the model found', async () => {
    const handlers = renderPanel()
    const addButtons = screen.getAllByRole('button', { name: 'Model Önerisini Listeme Ekle' })
    // model_only + detail_mismatch carry a model reference; human_only does not.
    expect(addButtons).toHaveLength(2)
    expect(screen.getByText('Sizde var, model bulamadı')).toBeInTheDocument()
    await userEvent.click(addButtons[0]!)
    expect(handlers.onAccept).toHaveBeenCalledWith(MODEL_ONLY, 0)
  })

  it('marks an already-accepted suggestion and disables its button', () => {
    renderPanel({ acceptedKeys: new Set([discrepancyKey(MODEL_ONLY, 0)]) })
    const accepted = screen.getByRole('button', { name: 'Eklendi' })
    expect(accepted).toBeDisabled()
  })

  it('warns when the model quote cannot be found in the document', () => {
    renderPanel({ result: makeResult({ discrepancies: [{ ...MODEL_ONLY, match_mode: null }] }) })
    expect(screen.getByText('Alıntı doküman metninde bulunamadı')).toBeInTheDocument()
  })

  it('names the differing fields for a detail mismatch', () => {
    renderPanel({ result: makeResult({ bucket: 'YELLOW', discrepancies: [DETAIL] }) })
    expect(screen.getByText('Referans ayrıntıları uyuşmuyor')).toBeInTheDocument()
    expect(screen.getAllByText(/fıkra/).length).toBeGreaterThan(0)
  })

  it('reports hover targets so the document can scroll', async () => {
    const handlers = renderPanel()
    const row = screen.getByTestId(`audit-row-${discrepancyKey(MODEL_ONLY, 0)}`)
    await userEvent.hover(row)
    expect(handlers.onHover).toHaveBeenCalledWith(discrepancyKey(MODEL_ONLY, 0))
    await userEvent.unhover(row)
    expect(handlers.onHover).toHaveBeenLastCalledWith(null)
  })

  it('wires the three free actions', async () => {
    const handlers = renderPanel()
    await userEvent.click(
      screen.getByRole('button', { name: 'Benim Etiketim Doğru, Yine de Tamamla' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Düzenlemeye Geri Dön' }))
    await userEvent.click(screen.getByRole('button', { name: 'Tamamla' }))
    expect(handlers.onOverride).toHaveBeenCalledTimes(1)
    expect(handlers.onBackToEdit).toHaveBeenCalledTimes(1)
    expect(handlers.onComplete).toHaveBeenCalledTimes(1)
  })

  it('shows the soft notice when a fresher prediction arrived', () => {
    renderPanel({
      staleNotice: 'Yeni model tahmini alındı, lütfen son kez teyit edip Tamamla\'ya basınız.',
    })
    expect(screen.getByRole('status')).toHaveTextContent('Yeni model tahmini alındı')
  })

  it('disables actions while a commit is in flight', () => {
    renderPanel({ isCompleting: true })
    expect(screen.getByRole('button', { name: 'Tamamla' })).toBeDisabled()
    expect(
      screen.getByRole('button', { name: 'Benim Etiketim Doğru, Yine de Tamamla' }),
    ).toBeDisabled()
  })
})
