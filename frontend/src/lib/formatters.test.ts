import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { formatRelativeTr } from './formatters'

describe('formatRelativeTr', () => {
  const NOW = new Date('2026-05-11T12:00:00Z')

  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(NOW)
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns "az önce" for less than a minute ago', () => {
    expect(formatRelativeTr('2026-05-11T11:59:30Z')).toBe('az önce')
  })

  it('returns Turkish relative for 2 hours ago', () => {
    const result = formatRelativeTr('2026-05-11T10:00:00Z')
    expect(result).toMatch(/saat önce/i)
  })

  it('returns Turkish relative for yesterday', () => {
    const result = formatRelativeTr('2026-05-10T12:00:00Z')
    expect(result).toMatch(/gün önce|1 gün/i)
  })

  it('returns "-" for null input', () => {
    expect(formatRelativeTr(null)).toBe('-')
  })

  it('returns "-" for invalid date', () => {
    expect(formatRelativeTr('not-a-date')).toBe('-')
  })
})
