import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { useCompleteAnnotationMutation, usePreAuditMutation } from '@/api/queries/annotations'
import { ApiError } from '@/api/client'
// Shared server: src/test/setup.ts already owns listen()/resetHandlers()/close().
// A second setupServer() in a test file installs a competing interceptor.
import { server } from '@/test/msw-server'

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

describe('usePreAuditMutation', () => {
  it('posts the current references and returns the audit result', async () => {
    const seen = vi.fn()
    server.use(
      http.post('http://localhost/api/annotations/:docId/pre-audit', async ({ request, params }) => {
        seen({ docId: params.docId, body: await request.json() })
        return HttpResponse.json({
          audit_status: 'ready',
          reason: null,
          bucket: 'RED',
          reasons: ['extra_or_different_core_reference'],
          similarity: 0.5,
          prediction_fingerprint: 'fp-1',
          model_generation: 'G0',
          discrepancies: [],
        })
      }),
    )
    const { result } = renderHook(() => usePreAuditMutation(), { wrapper })
    const audit = await result.current.mutateAsync({
      document_id: 'd1',
      references: [],
    })
    expect(audit.bucket).toBe('RED')
    expect(audit.prediction_fingerprint).toBe('fp-1')
    expect(seen).toHaveBeenCalledWith({ docId: 'd1', body: { references: [] } })
  })
})

describe('useCompleteAnnotationMutation', () => {
  it('sends audit_ack only when provided', async () => {
    const bodies: unknown[] = []
    server.use(
      http.post('http://localhost/api/annotations/:docId/complete', async ({ request }) => {
        bodies.push(await request.json())
        return HttpResponse.json({ ok: true })
      }),
    )
    const { result } = renderHook(() => useCompleteAnnotationMutation(), { wrapper })
    await result.current.mutateAsync({ document_id: 'd1', completed: true, references: [] })
    await result.current.mutateAsync({
      document_id: 'd1',
      completed: true,
      references: [],
      audit_ack: { prediction_fingerprint: 'fp-1' },
    })
    expect(bodies[0]).toEqual({ completed: true, references: [] })
    expect(bodies[1]).toEqual({
      completed: true,
      references: [],
      audit_ack: { prediction_fingerprint: 'fp-1' },
    })
  })

  it('surfaces audit_stale as a typed ApiError code', async () => {
    server.use(
      http.post('http://localhost/api/annotations/:docId/complete', () =>
        HttpResponse.json(
          {
            detail: {
              error: 'audit_stale',
              message: 'Yeni model tahmini alındı, lütfen son kez teyit edip Tamamla\'ya basınız.',
            },
          },
          { status: 409 },
        ),
      ),
    )
    const { result } = renderHook(() => useCompleteAnnotationMutation(), { wrapper })
    await expect(
      result.current.mutateAsync({ document_id: 'd1', completed: true, references: [] }),
    ).rejects.toMatchObject({ code: 'audit_stale' })
    await waitFor(() => expect(result.current.error).toBeInstanceOf(ApiError))
  })
})
