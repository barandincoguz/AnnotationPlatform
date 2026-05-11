import { describe, it, expect, vi } from 'vitest'
import {
  badgeUnlockedSchema, speedWarningSchema, charLimitWarningSchema,
  userOnlinePayloadSchema, userOfflinePayloadSchema, parseEventData,
} from './sseSchemas'

describe('badgeUnlockedSchema', () => {
  it('accepts the backend orchestrator payload', () => {
    const valid = {
      badge_id: 'first_annotation', name: 'İlk Annotation',
      description: 'İlk kayıt başarıyla yapıldı.',
      earned_at: '2026-05-11T16:00:00+00:00',
    }
    expect(() => badgeUnlockedSchema.parse(valid)).not.toThrow()
  })
})

describe('speedWarningSchema', () => {
  it('accepts the documented shape', () => {
    expect(() => speedWarningSchema.parse({ window_minutes: 5, save_count: 6 })).not.toThrow()
  })
  it('rejects float counters', () => {
    expect(() => speedWarningSchema.parse({ window_minutes: 5, save_count: 1.5 })).toThrow()
  })
})

describe('charLimitWarningSchema', () => {
  it('accepts ref_index + detail', () => {
    expect(() => charLimitWarningSchema.parse({ ref_index: 0, detail: '... çok uzun' })).not.toThrow()
  })
})

describe('userOnlinePayloadSchema', () => {
  it('accepts {id, username, avatar_color}', () => {
    expect(() => userOnlinePayloadSchema.parse({
      id: 1, username: 'x', avatar_color: '#abc',
    })).not.toThrow()
  })
})

describe('userOfflinePayloadSchema', () => {
  it('accepts {id}', () => {
    expect(() => userOfflinePayloadSchema.parse({ id: 1 })).not.toThrow()
  })
})

describe('parseEventData', () => {
  it('returns parsed data when JSON+schema match', () => {
    const e = new MessageEvent('badge_unlocked', {
      data: JSON.stringify({
        badge_id: 'x', name: 'y', description: 'z', earned_at: '2026-05-11',
      }),
    })
    const result = parseEventData(e, badgeUnlockedSchema)
    expect(result?.badge_id).toBe('x')
  })

  it('returns null on invalid JSON without throwing', () => {
    const e = new MessageEvent('badge_unlocked', { data: 'not-json' })
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    expect(parseEventData(e, badgeUnlockedSchema)).toBeNull()
    warn.mockRestore()
  })

  it('returns null on schema mismatch and warns', () => {
    const e = new MessageEvent('badge_unlocked', {
      data: JSON.stringify({ wrong: 'shape' }),
    })
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    expect(parseEventData(e, badgeUnlockedSchema)).toBeNull()
    expect(warn).toHaveBeenCalled()
    warn.mockRestore()
  })
})
