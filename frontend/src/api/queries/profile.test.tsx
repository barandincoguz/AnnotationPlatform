import { describe, it, expect } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { makeProfile } from '@/test/msw-handlers'
import { useProfile, profileKeys } from './profile'

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('useProfile', () => {
  it('fetches and parses profile data', async () => {
    server.use(
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json(makeProfile({ xp: { total: 999 } }))),
    )
    const { result } = renderHook(() => useProfile(), { wrapper: wrap() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.xp.total).toBe(999)
  })

  it('exposes profileKeys.me() for invalidations', () => {
    expect(profileKeys.me()).toEqual(['profile', 'me'])
  })

  it('surfaces Zod parse failure as query error', async () => {
    server.use(
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json({ broken: 'shape' })),
    )
    const { result } = renderHook(() => useProfile(), { wrapper: wrap() })
    await waitFor(() => expect(result.current.isError).toBe(true))
  })
})
