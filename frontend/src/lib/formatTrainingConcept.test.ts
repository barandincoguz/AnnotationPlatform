import { describe, it, expect } from 'vitest'
import { formatConcept } from './formatTrainingConcept'

describe('formatConcept', () => {
  it('formats required-only concept', () => {
    expect(formatConcept({ kanun_no: '5520', madde: '5' }))
      .toBe('Kanun No: 5520, Madde: 5')
  })

  it('formats required + optional', () => {
    expect(formatConcept({
      kanun_no: '5520', madde: '5', fikra: '1', bent: 'a',
    })).toBe('Kanun No: 5520, Madde: 5 (Fıkra: 1) (Bent: a)')
  })

  it('omits null/empty keys', () => {
    expect(formatConcept({
      kanun_no: '5520', kanun_ad: null, madde: '5', fikra: '',
      bent: undefined,
    })).toBe('Kanun No: 5520, Madde: 5')
  })

  it('handles kanun_ad-only concept', () => {
    expect(formatConcept({ kanun_ad: 'KVK' }))
      .toBe('Kanun Adı: KVK')
  })

  it('returns empty string for an empty concept', () => {
    expect(formatConcept({})).toBe('')
  })

  it('preserves Turkish characters', () => {
    expect(formatConcept({ kanun_no: '193', madde: 'Geçici 67' }))
      .toBe('Kanun No: 193, Madde: Geçici 67')
  })
})
