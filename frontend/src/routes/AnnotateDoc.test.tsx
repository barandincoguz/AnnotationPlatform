import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
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
})
