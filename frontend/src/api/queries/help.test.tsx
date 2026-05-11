import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { server } from '@/test/msw-server'
import { useHelpQuery } from './help'

const API = 'http://localhost'

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('useHelpQuery', () => {
  it('returns parsed sections on success', async () => {
    const { result } = renderHook(() => useHelpQuery(), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.sections.length).toBeGreaterThan(0)
    expect(result.current.data?.sections[0]).toMatchObject({
      id: expect.any(String),
      order: expect.any(Number),
      title: expect.any(String),
      body: expect.any(String),
    })
  })

  it('errors on malformed payload (zod parse fails)', async () => {
    server.use(http.get(`${API}/api/help`, () => HttpResponse.json({ wrong: 'shape' })))
    const { result } = renderHook(() => useHelpQuery(), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isError).toBe(true))
  })

  it('errors on network error', async () => {
    server.use(http.get(`${API}/api/help`, () => HttpResponse.error()))
    const { result } = renderHook(() => useHelpQuery(), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isError).toBe(true))
  })
})
