/* eslint-disable react/display-name -- test wrappers, no display name needed */
import { describe, expect, it } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { useUserStatistics, statisticsKeys } from './statistics'

const metrics = {
  distinct_documents: 0,
  save_events: 0,
  complete_events: 0,
  uncomplete_events: 0,
  skip_events: 0,
  version_events: 0,
  create_versions: 0,
  edit_versions: 0,
  complete_mark_versions: 0,
  zero_diff_versions: 0,
  final_completed_documents: 0,
  xp_delta: 0,
}

const periods = {
  today: metrics,
  last_7_days: metrics,
  last_30_days: metrics,
  all_time: metrics,
}

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('useUserStatistics', () => {
  it('fetches and parses user statistics', async () => {
    server.use(
      http.get('http://localhost/api/statistics/users', () =>
        HttpResponse.json({
          generated_at: '2026-07-06T12:00:00+00:00',
          summary: periods,
          users: [
            {
              user: { id: 1, username: 'alice', role: 'user', avatar_color: '#3b82f6' },
              xp_total: 42,
              badges_count: 1,
              streak_current: 3,
              last_active_date: '2026-07-06',
              metrics: periods,
            },
          ],
        }),
      ),
    )

    const { result } = renderHook(() => useUserStatistics(), { wrapper: wrap() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.users[0]?.xp_total).toBe(42)
  })

  it('exposes stable statistics query keys', () => {
    expect(statisticsKeys.users()).toEqual(['statistics', 'users'])
  })
})
