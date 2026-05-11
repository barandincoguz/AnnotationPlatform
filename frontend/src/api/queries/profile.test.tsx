import { describe, it, expect } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import type { ProfileResponse } from '@/lib/profileSchemas'
import { useProfile, profileKeys } from './profile'

function makeProfile(overrides: Partial<ProfileResponse> = {}): ProfileResponse {
  return {
    user: { id: 1, username: 'tester', role: 'user', avatar_color: '#3b82f6' },
    xp: { total: 0 },
    streak: { current: 0, longest: 0, last_active_date: null },
    today: { save: 0, complete: 0, review: 0, skip: 0, daily_target: 10 },
    badges: [],
    ...overrides,
  }
}

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
