import { describe, it, expect } from 'vitest'
import {
  profileResponseSchema, notificationSchema, notificationsListSchema,
  markAllReadResponseSchema, badgesCatalogItemSchema, badgesCatalogSchema,
  onlineUserSchema, onlineUsersSchema,
} from './profileSchemas'

describe('profileResponseSchema', () => {
  it('accepts a complete payload', () => {
    const valid = {
      user: { id: 1, username: 'tester', role: 'user', avatar_color: '#3b82f6' },
      xp: { total: 1240 },
      streak: { current: 3, longest: 12, last_active_date: '2026-05-11' },
      today: { save: 3, complete: 1, review: 0, skip: 0, daily_target: 10 },
      badges: [
        { id: 'first_annotation', name: 'İlk', description: 'Yapıldı.', earned_at: '2026-05-10T12:00:00+00:00' },
      ],
    }
    expect(profileResponseSchema.parse(valid)).toEqual(valid)
  })

  it('accepts null last_active_date (pre-save user)', () => {
    const valid = {
      user: { id: 2, username: 'newbie', role: 'user', avatar_color: '#22c55e' },
      xp: { total: 0 },
      streak: { current: 0, longest: 0, last_active_date: null },
      today: { save: 0, complete: 0, review: 0, skip: 0, daily_target: 10 },
      badges: [],
    }
    expect(() => profileResponseSchema.parse(valid)).not.toThrow()
  })

  it('rejects missing xp section', () => {
    const broken: unknown = {
      user: { id: 1, username: 'x', role: 'user', avatar_color: '#000' },
      streak: { current: 0, longest: 0, last_active_date: null },
      today: { save: 0, complete: 0, review: 0, skip: 0, daily_target: 0 },
      badges: [],
    }
    expect(() => profileResponseSchema.parse(broken)).toThrow()
  })
})

describe('notificationSchema', () => {
  it('accepts the backend shape (is_read + data field)', () => {
    const valid = {
      id: 42,
      kind: 'badge_unlocked',
      title: 'Yeni rozet: İlk Annotation',
      body: 'İlk kayıt başarıyla yapıldı.',
      data: { badge_id: 'first_annotation' },
      is_read: false,
      created_at: '2026-05-11T16:00:00+00:00',
    }
    expect(notificationSchema.parse(valid)).toEqual(valid)
  })

  it('accepts null body + null data', () => {
    const valid = {
      id: 7, kind: 'training_passed', title: 'OK', body: null,
      data: null, is_read: true, created_at: '2026-05-11T00:00:00+00:00',
    }
    expect(() => notificationSchema.parse(valid)).not.toThrow()
  })

  it('rejects when is_read is missing', () => {
    const broken: unknown = {
      id: 1, kind: 'x', title: 'y', body: null, data: null,
      created_at: '2026-05-11T00:00:00+00:00',
    }
    expect(() => notificationSchema.parse(broken)).toThrow()
  })
})

describe('notificationsListSchema', () => {
  it('wraps items array', () => {
    expect(notificationsListSchema.parse({ items: [] })).toEqual({ items: [] })
  })
})

describe('markAllReadResponseSchema', () => {
  it('requires marked_count integer', () => {
    expect(markAllReadResponseSchema.parse({ marked_count: 5 })).toEqual({ marked_count: 5 })
    expect(() => markAllReadResponseSchema.parse({ marked_count: 1.5 })).toThrow()
  })
})

describe('badgesCatalogSchema', () => {
  it('accepts an entry with criterion', () => {
    const valid = [{
      id: 'first_annotation', name: 'İlk Annotation',
      description: 'İlk kayıt başarıyla yapıldı.',
      criterion: 'İlk anotasyon kaydını yap.',
    }]
    expect(badgesCatalogSchema.parse(valid)).toEqual(valid)
  })

  it('accepts an entry without criterion (defensive)', () => {
    const valid = [{ id: 'x', name: 'X', description: 'Y' }]
    expect(() => badgesCatalogSchema.parse(valid)).not.toThrow()
  })

  it('individual item schema rejects missing id', () => {
    expect(() => badgesCatalogItemSchema.parse({ name: 'x', description: 'y' })).toThrow()
  })
})

describe('onlineUsersSchema', () => {
  it('accepts empty array', () => {
    expect(onlineUsersSchema.parse([])).toEqual([])
  })

  it('individual user shape', () => {
    const valid = { id: 1, username: 'tester', avatar_color: '#3b82f6' }
    expect(onlineUserSchema.parse(valid)).toEqual(valid)
  })
})
