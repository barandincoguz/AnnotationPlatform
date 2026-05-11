import { describe, it, expect } from 'vitest'
import { iconForKind, NOTIFICATION_KIND_ICONS } from './notificationKinds'

describe('iconForKind', () => {
  it('returns specific icon for known kinds', () => {
    expect(iconForKind('badge_unlocked')).toBe('🏆')
    expect(iconForKind('training_passed')).toBe('🎓')
    expect(iconForKind('training_reset')).toBe('🔄')
    expect(iconForKind('admin_announcement')).toBe('📢')
    expect(iconForKind('lock_lost')).toBe('🔓')
  })

  it('returns generic 🔔 for unknown kinds', () => {
    expect(iconForKind('something_new')).toBe('🔔')
    expect(iconForKind('')).toBe('🔔')
  })
})

describe('NOTIFICATION_KIND_ICONS', () => {
  it('exposes a record where every value is a non-empty string', () => {
    for (const v of Object.values(NOTIFICATION_KIND_ICONS)) {
      expect(typeof v).toBe('string')
      expect(v.length).toBeGreaterThanOrEqual(1)
    }
  })
})
