import { describe, it, expect } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { useBadgesCatalog, useLockedBadges, badgesKeys } from './badges'

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

function catalogSample() {
  return [
    { id: 'first_annotation', name: 'A', description: 'a desc', criterion: 'a crit' },
    { id: 'annotations_10', name: 'B', description: 'b desc', criterion: 'b crit' },
    { id: 'marathoner', name: 'C', description: 'c desc', criterion: 'c crit' },
  ]
}

describe('useBadgesCatalog', () => {
  it('fetches and parses the catalog', async () => {
    server.use(
      http.get('http://localhost/api/badges/catalog', () =>
        HttpResponse.json(catalogSample())),
    )
    const { result } = renderHook(() => useBadgesCatalog(), { wrapper: wrap() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.length).toBe(3)
  })

  it('exposes stable query key', () => {
    expect(badgesKeys.catalog()).toEqual(['badges', 'catalog'])
  })
})

describe('useLockedBadges', () => {
  it('returns catalog entries NOT in earned set', async () => {
    server.use(
      http.get('http://localhost/api/badges/catalog', () =>
        HttpResponse.json(catalogSample())),
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json({
          user: { id: 1, username: 'x', role: 'user', avatar_color: '#000' },
          xp: { total: 0 },
          streak: { current: 0, longest: 0, last_active_date: null },
          today: { save: 0, complete: 0, review: 0, skip: 0, daily_target: 0 },
          badges: [{
            id: 'first_annotation', name: 'A', description: 'a desc',
            earned_at: '2026-05-11T00:00:00+00:00',
          }],
        })),
    )
    const { result } = renderHook(() => useLockedBadges(), { wrapper: wrap() })
    await waitFor(() => expect(result.current.length).toBe(2))
    expect(result.current.map((b) => b.id)).toEqual(['annotations_10', 'marathoner'])
  })

  it('returns [] while either query is loading', () => {
    const { result } = renderHook(() => useLockedBadges(), { wrapper: wrap() })
    expect(result.current).toEqual([])
  })
})
