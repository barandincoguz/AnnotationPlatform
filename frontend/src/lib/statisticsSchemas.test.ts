import { describe, expect, it } from 'vitest'
import {
  STATISTICS_PERIODS,
  statisticsMetricsSchema,
  statisticsResponseSchema,
} from './statisticsSchemas'

const zeroMetrics = {
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

function periodMap(overrides = {}) {
  return Object.fromEntries(
    STATISTICS_PERIODS.map((period) => [period, { ...zeroMetrics, ...overrides }]),
  )
}

describe('statistics schemas', () => {
  it('accepts the backend statistics response shape', () => {
    const valid = {
      generated_at: '2026-07-06T12:00:00+00:00',
      summary: periodMap({ save_events: 3 }),
      users: [
        {
          user: { id: 1, username: 'alice', role: 'user', avatar_color: '#3b82f6' },
          xp_total: 10,
          badges_count: 1,
          streak_current: 2,
          last_active_date: '2026-07-06',
          metrics: periodMap({ distinct_documents: 2 }),
        },
      ],
    }

    expect(statisticsResponseSchema.parse(valid)).toEqual(valid)
  })

  it('rejects missing metric fields', () => {
    expect(() => statisticsMetricsSchema.parse({ save_events: 1 })).toThrow()
  })
})
