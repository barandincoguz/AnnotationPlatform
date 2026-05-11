import { describe, it, expect } from 'vitest'
import { isValidReference, areAllReferencesValid } from './validateReferences'

const ref = (overrides: Record<string, unknown> = {}) => ({
  kanun_no: null,
  kanun_ad: null,
  madde: null,
  fikra: null,
  bent: null,
  source_text: '',
  ...overrides,
})

describe('isValidReference', () => {
  it('rejects empty source_text', () => {
    expect(isValidReference(ref({ kanun_no: '5520', source_text: '' }))).toBe(false)
    expect(isValidReference(ref({ kanun_no: '5520', source_text: '   ' }))).toBe(false)
  })

  it('rejects when neither kanun_no nor kanun_ad is present', () => {
    expect(isValidReference(ref({ source_text: 'metin' }))).toBe(false)
  })

  it('rejects when both kanun_no and kanun_ad are blank strings', () => {
    expect(isValidReference(ref({ kanun_no: '  ', kanun_ad: '  ', source_text: 'metin' }))).toBe(false)
  })

  it('accepts when kanun_no is present', () => {
    expect(isValidReference(ref({ kanun_no: '5520', source_text: 'metin' }))).toBe(true)
  })

  it('accepts when only kanun_ad is present (no kanun_no)', () => {
    expect(isValidReference(ref({ kanun_ad: 'Kurumlar Vergisi Kanunu', source_text: 'metin' }))).toBe(true)
  })

  it('accepts when both kanun_no and kanun_ad are present', () => {
    expect(isValidReference(ref({ kanun_no: '5520', kanun_ad: 'KVK', source_text: 'metin' }))).toBe(true)
  })
})

describe('areAllReferencesValid', () => {
  it('empty list is valid (zero-ref legal case)', () => {
    expect(areAllReferencesValid([])).toBe(true)
  })

  it('all valid → true', () => {
    expect(areAllReferencesValid([
      ref({ kanun_no: '5520', source_text: 'a' }),
      ref({ kanun_ad: 'KVK', source_text: 'b' }),
    ])).toBe(true)
  })

  it('one invalid → false', () => {
    expect(areAllReferencesValid([
      ref({ kanun_no: '5520', source_text: 'a' }),
      ref({ source_text: 'b' }), // missing kanun_*
    ])).toBe(false)
  })
})
