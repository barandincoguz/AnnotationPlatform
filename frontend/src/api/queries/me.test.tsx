import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { server } from '@/test/msw-server'
import { useSeenManualMutation } from './me'

const API = 'http://localhost'

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
  Wrapper.displayName = 'TestWrapper'
  return Wrapper
}

describe('useSeenManualMutation', () => {
  it('POSTs /api/me/seen-manual and resolves on success', async () => {
    let called = false
    server.use(
      http.post(`${API}/api/me/seen-manual`, () => {
        called = true
        return HttpResponse.json({ ok: true })
      }),
    )
    const { result } = renderHook(() => useSeenManualMutation(), { wrapper: createWrapper() })
    await result.current.mutateAsync()
    await waitFor(() => expect(called).toBe(true))
  })

  it('rejects on 500', async () => {
    server.use(
      http.post(`${API}/api/me/seen-manual`, () =>
        HttpResponse.json({ detail: { error: 'boom', message: 'x' } }, { status: 500 }),
      ),
    )
    const { result } = renderHook(() => useSeenManualMutation(), { wrapper: createWrapper() })
    await expect(result.current.mutateAsync()).rejects.toBeDefined()
  })
})
