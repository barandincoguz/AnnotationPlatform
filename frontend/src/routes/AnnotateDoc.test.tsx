import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { renderWithProviders } from '@/test/render'
import { makeDocumentDetail } from '@/test/msw-handlers'
import { useAuthStore } from '@/stores/authStore'
import { AnnotateDoc } from './AnnotateDoc'

beforeEach(() => {
  useAuthStore.getState().setUser({
    id: 1,
    username: 'tester',
    email: null,
    role: 'user',
    is_active: true,
    has_seen_manual: true,
    has_passed_training: true,
    avatar_color: null,
    created_at: '2026-05-01T00:00:00+00:00',
  })
})

function renderDoc(initialPath: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/docs/:docId" element={<AnnotateDoc />} />
      <Route path="/" element={<div data-testid="route-root" />} />
    </Routes>,
    {
      initialEntries: [initialPath],
      wildcardEntry: true,
    },
  )
}

describe('AnnotateDoc integration', () => {
  it('mounts, acquires lock, displays doc body + ref panel ready', async () => {
    server.use(
      http.get('http://localhost/api/documents/doc-1', () =>
        HttpResponse.json(
          makeDocumentDetail({
            document_id: 'doc-1',
            pdf_text: 'BELGE METNİ XYZ',
          }),
        ),
      ),
    )
    renderDoc('/docs/doc-1')
    await waitFor(() => expect(screen.getByText(/BELGE METNİ XYZ/i)).toBeInTheDocument(), {
      timeout: 3000,
    })
    await waitFor(
      () => {
        const btn = screen.getByRole('button', { name: /yeni referans/i })
        expect(btn).not.toBeDisabled()
      },
      { timeout: 3000 },
    )
  })

  it('does not expose editing before reference hydration completes', async () => {
    let resolveDraft!: () => void
    let resolveAnnotation!: () => void
    const draftGate = new Promise<void>((resolve) => {
      resolveDraft = resolve
    })
    const annotationGate = new Promise<void>((resolve) => {
      resolveAnnotation = resolve
    })
    server.use(
      http.get('http://localhost/api/drafts/doc-1', async () => {
        await draftGate
        return HttpResponse.json({ detail: 'not found' }, { status: 404 })
      }),
      http.get('http://localhost/api/documents/doc-1/annotation', async () => {
        await annotationGate
        return HttpResponse.json({ annotation: null, chain: [] })
      }),
    )

    renderDoc('/docs/doc-1')

    expect(
      await screen.findByText(/referanslar yükleniyor/i),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /yeni referans/i }),
    ).not.toBeInTheDocument()

    resolveDraft()
    resolveAnnotation()

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /yeni referans/i }),
      ).not.toBeDisabled()
    })
  })

  it('blocks editing and offers retry when reference hydration fails', async () => {
    server.use(
      http.get('http://localhost/api/drafts/doc-1', () =>
        HttpResponse.json({ detail: 'temporary failure' }, { status: 503 }),
      ),
    )

    renderDoc('/docs/doc-1')

    expect(
      await screen.findByRole('heading', { name: /referanslar yüklenemedi/i }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /yeni referans/i }),
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /yeniden dene/i }),
    ).toBeInTheDocument()
  })

  it('shows LockConflictModal on 409 acquire (different user)', async () => {
    server.use(
      http.post('http://localhost/api/locks/doc-1/acquire', () =>
        HttpResponse.json(
          {
            detail: {
              error: 'lock_held_by_other',
              by_user_id: 99,
              by_username: 'ahmet',
              acquired_at: '2026-05-11T10:00:00+00:00',
              expires_at: '2026-05-11T10:01:30+00:00',
            },
          },
          { status: 409 },
        ),
      ),
    )
    renderDoc('/docs/doc-1')
    await waitFor(() => expect(screen.getByText(/ahmet/i)).toBeInTheDocument(), { timeout: 5000 })
    expect(screen.getByText(/düzenliyor/i)).toBeInTheDocument()
  })

  it('shows a recoverable error when lock acquisition fails', async () => {
    let attempts = 0
    server.use(
      http.post('http://localhost/api/locks/doc-1/acquire', () => {
        attempts++
        if (attempts === 1) {
          return HttpResponse.json({ detail: 'temporary failure' }, { status: 503 })
        }
        return HttpResponse.json({
          document_id: 'doc-1',
          user_id: 1,
          by_username: 'tester',
          acquired_at: '2026-05-11T10:00:00+00:00',
          expires_at: '2026-05-11T10:01:30+00:00',
        })
      }),
    )
    const user = userEvent.setup()
    renderDoc('/docs/doc-1')

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /düzenleme kilidi alınamadı/i })).toBeInTheDocument(),
    )
    await user.click(screen.getByRole('button', { name: /yeniden dene/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /yeni referans/i })).not.toBeDisabled()
    })
    expect(attempts).toBe(2)
  })

  it('Skip button calls POST /skip', async () => {
    const skipSpy = vi.fn(() => HttpResponse.json({ ok: true }))
    server.use(http.post('http://localhost/api/annotations/doc-1/skip', skipSpy))
    const user = userEvent.setup()
    renderDoc('/docs/doc-1')
    await waitFor(
      () => {
        const btn = screen.getByRole('button', { name: /atla/i })
        expect(btn).not.toBeDisabled()
      },
      { timeout: 3000 },
    )
    await user.click(screen.getByRole('button', { name: /atla/i }))
    await waitFor(() => expect(skipSpy).toHaveBeenCalled())
  })

  // === Phase 3: handleComplete collapses to a single atomic POST ===
  //
  // Pre-Phase-2 the frontend ran save → complete → delete_draft in a
  // chain. After Phase 2 the backend handles all three inside one
  // BEGIN IMMEDIATE when refs are passed in the complete body. This
  // test verifies the frontend uses the new contract and does NOT
  // fall back to the legacy save call.

  it('Complete sends refs in a single POST /complete and skips legacy save endpoint', async () => {
    // Hydrate an annotation row with one ref so refs.list is populated
    // when the Tamamla button is clicked.
    server.use(
      http.get('http://localhost/api/documents/doc-1', () =>
        HttpResponse.json(
          makeDocumentDetail({ document_id: 'doc-1', pdf_text: 'BELGE' }),
        ),
      ),
      http.get('http://localhost/api/documents/doc-1/annotation', () =>
        HttpResponse.json({
          annotation: {
            document_id: 'doc-1',
            references: [
              {
                kanun_no: '193',
                kanun_ad: null,
                madde: '37',
                fikra: null,
                bent: null,
                source_text: 'on-screen ref',
              },
            ],
            is_completed: false,
            last_editor_user_id: 1,
            completed_by_user_id: null,
            edit_count: 1,
            unique_users_count: 1,
            created_at: '2026-05-17T00:00:00+00:00',
            updated_at: '2026-05-17T00:00:00+00:00',
          },
          chain: [],
        }),
      ),
    )

    // Spies for both endpoints — assert the legacy save was NOT hit
    // while complete WAS hit with refs in the body.
    const saveSpy = vi.fn(() => HttpResponse.json({ ok: true }))
    let completeBody: unknown = null
    const completeSpy = vi.fn(async ({ request }: { request: Request }) => {
      completeBody = await request.json()
      return HttpResponse.json({ ok: true })
    })
    server.use(
      http.post('http://localhost/api/annotations', saveSpy),
      http.post('http://localhost/api/annotations/doc-1/complete', completeSpy),
    )

    const user = userEvent.setup()
    renderDoc('/docs/doc-1')
    await waitFor(
      () => {
        const btn = screen.getByRole('button', { name: /^tamamla$/i })
        expect(btn).not.toBeDisabled()
      },
      { timeout: 3000 },
    )
    await user.click(screen.getByRole('button', { name: /^tamamla$/i }))

    await waitFor(() => expect(completeSpy).toHaveBeenCalledTimes(1))
    // Legacy save endpoint MUST NOT have been hit — that was the
    // pre-Phase-2 chain step we just collapsed.
    expect(saveSpy).not.toHaveBeenCalled()
    // Body carried refs alongside the flag.
    const body = completeBody as { completed: boolean; references: { source_text: string }[] }
    expect(body.completed).toBe(true)
    expect(body.references).toHaveLength(1)
    expect(body.references[0]?.source_text).toBe('on-screen ref')
  })

  it('Uncomplete (completed=false) omits refs from the complete body', async () => {
    // Already-completed annotation — clicking the (now-rendered)
    // "Tamamlanmayı geri al" button must send `{completed: false}`
    // with NO references key (the backend would 422 otherwise).
    server.use(
      http.get('http://localhost/api/documents/doc-1', () =>
        HttpResponse.json(
          makeDocumentDetail({ document_id: 'doc-1', pdf_text: 'BELGE' }),
        ),
      ),
      http.get('http://localhost/api/documents/doc-1/annotation', () =>
        HttpResponse.json({
          annotation: {
            document_id: 'doc-1',
            references: [
              {
                kanun_no: '193',
                kanun_ad: null,
                madde: '37',
                fikra: null,
                bent: null,
                source_text: 'prior',
              },
            ],
            is_completed: true,
            last_editor_user_id: 1,
            completed_by_user_id: 1,
            edit_count: 1,
            unique_users_count: 1,
            created_at: '2026-05-17T00:00:00+00:00',
            updated_at: '2026-05-17T00:00:00+00:00',
          },
          chain: [],
        }),
      ),
    )

    let completeBody: Record<string, unknown> | null = null
    const completeSpy = vi.fn(async ({ request }: { request: Request }) => {
      completeBody = (await request.json()) as Record<string, unknown>
      return HttpResponse.json({ ok: true })
    })
    server.use(
      http.post('http://localhost/api/annotations/doc-1/complete', completeSpy),
    )

    const user = userEvent.setup()
    renderDoc('/docs/doc-1')
    await waitFor(
      () => {
        // The uncomplete button has a different label — it shows
        // when isCompleted=true.
        const btn = screen.getByRole('button', { name: /geri al/i })
        expect(btn).not.toBeDisabled()
      },
      { timeout: 3000 },
    )
    await user.click(screen.getByRole('button', { name: /geri al/i }))

    await waitFor(() => expect(completeSpy).toHaveBeenCalledTimes(1))
    expect(completeBody).toEqual({ completed: false })
    // No `references` key in the uncomplete payload.
    expect(completeBody).not.toHaveProperty('references')
  })

  it('shows lost lock screen and allows retry', async () => {
    let acquireAttempts = 0
    server.use(
      http.post('http://localhost/api/locks/doc-1/acquire', () => {
        acquireAttempts++
        return HttpResponse.json({
          document_id: 'doc-1',
          user_id: 1,
          by_username: 'tester',
          acquired_at: '2026-05-11T10:00:00+00:00',
          expires_at: '2026-05-11T10:01:30+00:00',
        })
      }),
      http.post('http://localhost/api/locks/doc-1/heartbeat', () => {
        return HttpResponse.json({ detail: 'not lock holder' }, { status: 404 })
      }),
    )

    const user = userEvent.setup()
    
    vi.useFakeTimers({ shouldAdvanceTime: true })
    
    try {
      renderDoc('/docs/doc-1')
      
      await waitFor(() => expect(screen.getByRole('button', { name: /yeni referans/i })).toBeInTheDocument())
      
      await act(async () => {
        await vi.advanceTimersByTimeAsync(35_000)
      })

      await waitFor(() =>
        expect(screen.getByRole('heading', { name: /düzenleme kilidi kaybedildi/i })).toBeInTheDocument()
      )

      vi.useRealTimers()

      await user.click(screen.getByRole('button', { name: /yeniden kilitle/i }))

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /yeni referans/i })).not.toBeDisabled()
      })
      
      expect(acquireAttempts).toBe(2)
    } finally {
      vi.useRealTimers()
    }
  })
})
