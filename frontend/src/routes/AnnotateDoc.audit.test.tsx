import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { makeDocumentDetail } from '@/test/msw-handlers'
import { server } from '@/test/msw-server'
import { renderWithProviders } from '@/test/render'
import { useAuthStore } from '@/stores/authStore'
import { AnnotateDoc } from './AnnotateDoc'

const PDF_TEXT =
  "Vergi Usul Kanunu'nun 114 uncu maddesinde zamanasimi hukmu duzenlenmistir. " +
  'Gelir Vergisi Kanunu 94 uncu maddesi tevkifat esaslarini belirler.'

const MODEL_ONLY_DISCREPANCY = {
  kind: 'model_only' as const,
  kanun_no: '193',
  kanun_ad: 'Gelir Vergisi Kanunu',
  madde: '94',
  model_reference: {
    kanun_no: '193', kanun_ad: 'Gelir Vergisi Kanunu', madde: '94',
    fikra: '', bent: '', source_text: 'tevkifat esaslarini belirler',
  },
  human_reference: null,
  field_diffs: [],
  match_mode: 'normalized_exact',
}

function redAudit(fingerprint = 'fp-1') {
  return {
    audit_status: 'ready',
    reason: null,
    bucket: 'RED',
    reasons: ['extra_or_different_core_reference'],
    similarity: 0.5,
    prediction_fingerprint: fingerprint,
    model_generation: 'G0',
    discrepancies: [MODEL_ONLY_DISCREPANCY],
  }
}

function greenAudit(fingerprint = 'fp-1') {
  return { ...redAudit(fingerprint), bucket: 'GREEN', reasons: [], discrepancies: [] }
}

function unavailableAudit() {
  return {
    audit_status: 'model_unavailable',
    reason: 'no_prediction',
    bucket: null,
    reasons: [],
    similarity: null,
    prediction_fingerprint: null,
    model_generation: null,
    discrepancies: [],
  }
}

beforeEach(() => {
  useAuthStore.getState().setUser({
    id: 1, username: 'tester', email: null, role: 'user', is_active: true,
    has_seen_manual: true, has_passed_training: true, avatar_color: null,
    created_at: '2026-05-01T00:00:00+00:00',
  })
  server.use(
    http.get('http://localhost/api/documents/doc-1', () =>
      HttpResponse.json(makeDocumentDetail({ document_id: 'doc-1', pdf_text: PDF_TEXT })),
    ),
    http.get('http://localhost/api/documents/doc-1/annotation', () =>
      HttpResponse.json({
        annotation: {
          document_id: 'doc-1',
          references: [{
            kanun_no: '213', kanun_ad: 'Vergi Usul Kanunu', madde: '114',
            fikra: null, bent: null, source_text: 'zamanasimi hukmu duzenlenmistir',
          }],
          is_completed: false,
          last_editor_user_id: 1,
          completed_by_user_id: null,
          edit_count: 1,
          unique_users_count: 1,
          created_at: '2026-08-01T00:00:00Z',
          updated_at: '2026-08-01T00:00:00Z',
        },
        chain: [],
      }),
    ),
  )
})

function renderDoc() {
  return renderWithProviders(
    <Routes>
      <Route path="/docs/:docId" element={<AnnotateDoc />} />
      <Route path="/" element={<div data-testid="route-root" />} />
    </Routes>,
    { initialEntries: ['/docs/doc-1'], wildcardEntry: true },
  )
}

async function clickComplete() {
  const button = await screen.findByRole('button', { name: /^tamamlandı$/i })
  await waitFor(() => expect(button).not.toBeDisabled())
  await userEvent.click(button)
}

describe('AnnotateDoc quality audit', () => {
  it('opens the audit panel instead of completing when the buckets mismatch', async () => {
    const completes: unknown[] = []
    server.use(
      http.post('http://localhost/api/annotations/doc-1/pre-audit', () =>
        HttpResponse.json(redAudit()),
      ),
      http.post('http://localhost/api/annotations/doc-1/complete', async ({ request }) => {
        completes.push(await request.json())
        return HttpResponse.json({ ok: true })
      }),
    )
    renderDoc()
    await clickComplete()
    expect(
      await screen.findByText('Model Karşılaştırma & Kalite Denetimi'),
    ).toBeInTheDocument()
    expect(completes).toHaveLength(0)
  })

  it('marks the model quote in the document body while the panel is open', async () => {
    server.use(
      http.post('http://localhost/api/annotations/doc-1/pre-audit', () =>
        HttpResponse.json(redAudit()),
      ),
    )
    renderDoc()
    await clickComplete()
    await screen.findByText('Model Karşılaştırma & Kalite Denetimi')
    await waitFor(() => {
      const mark = document.querySelector('mark')
      expect(mark?.textContent).toBe('tevkifat esaslarini belirler')
    })
  })

  it('completes straight through when the audit is green', async () => {
    const completes: Record<string, unknown>[] = []
    server.use(
      http.post('http://localhost/api/annotations/doc-1/pre-audit', () =>
        HttpResponse.json(greenAudit()),
      ),
      http.post('http://localhost/api/annotations/doc-1/complete', async ({ request }) => {
        completes.push((await request.json()) as Record<string, unknown>)
        return HttpResponse.json({ ok: true })
      }),
    )
    renderDoc()
    await clickComplete()
    await waitFor(() => expect(completes).toHaveLength(1))
    expect(completes[0]!.audit_ack).toEqual({ prediction_fingerprint: 'fp-1' })
    expect(screen.queryByText('Model Karşılaştırma & Kalite Denetimi')).toBeNull()
  })

  it('completes without an ack and shows a neutral notice when no prediction exists', async () => {
    const completes: Record<string, unknown>[] = []
    server.use(
      http.post('http://localhost/api/annotations/doc-1/pre-audit', () =>
        HttpResponse.json(unavailableAudit()),
      ),
      http.post('http://localhost/api/annotations/doc-1/complete', async ({ request }) => {
        completes.push((await request.json()) as Record<string, unknown>)
        return HttpResponse.json({ ok: true })
      }),
    )
    renderDoc()
    await clickComplete()
    await waitFor(() => expect(completes).toHaveLength(1))
    expect(completes[0]!.audit_ack).toBeUndefined()
  })

  it('accepting a suggestion and immediately completing sends the accepted reference', async () => {
    const completes: { references?: Record<string, unknown>[] }[] = []
    let auditCalls = 0
    server.use(
      http.post('http://localhost/api/annotations/doc-1/pre-audit', () => {
        auditCalls += 1
        return HttpResponse.json(auditCalls === 1 ? redAudit() : greenAudit())
      }),
      http.post('http://localhost/api/annotations/doc-1/complete', async ({ request }) => {
        completes.push((await request.json()) as { references?: Record<string, unknown>[] })
        return HttpResponse.json({ ok: true })
      }),
    )
    renderDoc()
    await clickComplete()
    await screen.findByText('Model Karşılaştırma & Kalite Denetimi')
    // No waiting between accept and complete: this is the debounce race (rule 2).
    await userEvent.click(
      screen.getByRole('button', { name: 'Model Önerisini Listeme Ekle' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Tamamla' }))
    await waitFor(() => expect(completes).toHaveLength(1))
    const sent = completes[0]!.references ?? []
    expect(sent).toHaveLength(2)
    expect(sent.map((r) => r.madde)).toContain('94')
  })

  it('override commits immediately with the ack', async () => {
    const completes: Record<string, unknown>[] = []
    server.use(
      http.post('http://localhost/api/annotations/doc-1/pre-audit', () =>
        HttpResponse.json(redAudit()),
      ),
      http.post('http://localhost/api/annotations/doc-1/complete', async ({ request }) => {
        completes.push((await request.json()) as Record<string, unknown>)
        return HttpResponse.json({ ok: true })
      }),
    )
    renderDoc()
    await clickComplete()
    await screen.findByText('Model Karşılaştırma & Kalite Denetimi')
    await userEvent.click(
      screen.getByRole('button', { name: 'Benim Etiketim Doğru, Yine de Tamamla' }),
    )
    await waitFor(() => expect(completes).toHaveLength(1))
    expect(completes[0]!.audit_ack).toEqual({ prediction_fingerprint: 'fp-1' })
  })

  it('recovers softly from 409 audit_stale by re-auditing and reopening the panel', async () => {
    let auditCalls = 0
    server.use(
      http.post('http://localhost/api/annotations/doc-1/pre-audit', () => {
        auditCalls += 1
        // First call: green (so the flow tries to commit). Second call (after
        // the 409): the agent's fresher prediction disagrees.
        return HttpResponse.json(auditCalls === 1 ? greenAudit('fp-1') : redAudit('fp-2'))
      }),
      http.post('http://localhost/api/annotations/doc-1/complete', () =>
        HttpResponse.json(
          {
            detail: {
              error: 'audit_stale',
              message: 'Yeni model tahmini alındı, lütfen son kez teyit edip Tamamla\'ya basınız.',
              prediction_fingerprint: 'fp-2',
            },
          },
          { status: 409 },
        ),
      ),
    )
    renderDoc()
    await clickComplete()
    expect(await screen.findByRole('status')).toHaveTextContent('Yeni model tahmini alındı')
    expect(screen.getByText('Model Karşılaştırma & Kalite Denetimi')).toBeInTheDocument()
  })

  it('lets the user compare on demand without completing', async () => {
    const completes: unknown[] = []
    server.use(
      http.post('http://localhost/api/annotations/doc-1/pre-audit', () =>
        HttpResponse.json(redAudit()),
      ),
      http.post('http://localhost/api/annotations/doc-1/complete', async ({ request }) => {
        completes.push(await request.json())
        return HttpResponse.json({ ok: true })
      }),
    )
    renderDoc()
    const compare = await screen.findByRole('button', { name: 'Model ile karşılaştır' })
    await waitFor(() => expect(compare).not.toBeDisabled())
    await userEvent.click(compare)
    expect(
      await screen.findByText('Model Karşılaştırma & Kalite Denetimi'),
    ).toBeInTheDocument()
    expect(completes).toHaveLength(0)
  })

  it('returns to editing from the panel', async () => {
    server.use(
      http.post('http://localhost/api/annotations/doc-1/pre-audit', () =>
        HttpResponse.json(redAudit()),
      ),
    )
    renderDoc()
    await clickComplete()
    await screen.findByText('Model Karşılaştırma & Kalite Denetimi')
    await userEvent.click(screen.getByRole('button', { name: 'Düzenlemeye Geri Dön' }))
    await waitFor(() =>
      expect(screen.queryByText('Model Karşılaştırma & Kalite Denetimi')).toBeNull(),
    )
    expect(screen.getByRole('button', { name: /yeni referans/i })).toBeInTheDocument()
  })
})
