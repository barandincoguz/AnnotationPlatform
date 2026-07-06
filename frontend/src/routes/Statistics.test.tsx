import { describe, expect, it } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { renderWithProviders } from '@/test/render'
import { Statistics } from './Statistics'

const baseMetrics = {
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

function metrics(overrides: Partial<typeof baseMetrics> = {}) {
  return { ...baseMetrics, ...overrides }
}

function periods(allTime: Partial<typeof baseMetrics>, last7: Partial<typeof baseMetrics> = {}) {
  return {
    today: metrics({ save_events: 1 }),
    last_7_days: metrics(last7),
    last_30_days: metrics({ distinct_documents: 7 }),
    all_time: metrics(allTime),
  }
}

describe('Statistics route', () => {
  it('renders summary cards, switches period, and filters users', async () => {
    server.use(
      http.get('http://localhost/api/statistics/users', () =>
        HttpResponse.json({
          generated_at: '2026-07-06T12:00:00+00:00',
          summary: periods(
            { distinct_documents: 10, save_events: 8, complete_events: 4, xp_delta: 90 },
            { distinct_documents: 3, save_events: 2, complete_events: 1, xp_delta: 20 },
          ),
          users: [
            {
              user: { id: 1, username: 'alice', role: 'user', avatar_color: '#3b82f6' },
              xp_total: 50,
              badges_count: 2,
              streak_current: 5,
              last_active_date: '2026-07-06',
              metrics: periods({ distinct_documents: 8, save_events: 6 }),
            },
            {
              user: { id: 2, username: 'bob', role: 'user', avatar_color: '#22c55e' },
              xp_total: 40,
              badges_count: 1,
              streak_current: 0,
              last_active_date: null,
              metrics: periods({ distinct_documents: 2, save_events: 2 }),
            },
          ],
        }),
      ),
    )

    renderWithProviders(<Statistics />)

    expect(await screen.findByRole('heading', { name: 'Kullanıcı İstatistikleri' }))
      .toBeInTheDocument()
    expect(await screen.findByLabelText('Özet kaydedilen doküman sayısı')).toHaveTextContent('8')

    const user = userEvent.setup()
    await user.click(screen.getByRole('tab', { name: /son 7 gün/i }))
    expect(screen.getByLabelText('Özet kaydedilen doküman sayısı')).toHaveTextContent('2')

    await user.type(screen.getByLabelText(/kullanıcı ara/i), 'bob')
    await waitFor(() => {
      expect(screen.queryByText('alice')).not.toBeInTheDocument()
      expect(screen.getByText('bob')).toBeInTheDocument()
    })
  })
})
