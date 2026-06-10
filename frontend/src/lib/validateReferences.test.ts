import { describe, it, expect } from 'vitest'
import {
  isValidReference, areAllReferencesValid,
  isValidTrainingReference, areAllTrainingReferencesValid,
  parseComplexMadde,
  normalizeTurkishKey, normalizeKanunAdi, normalizeIdentifier,
} from './validateReferences'

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

describe('isValidTrainingReference (16c.1)', () => {
  it('accepts a reference with kanun_no even when source_text is empty', () => {
    expect(isValidTrainingReference(ref({
      kanun_no: '5520', madde: '5', source_text: '',
    }))).toBe(true)
  })

  it('accepts a reference with kanun_ad-only', () => {
    expect(isValidTrainingReference(ref({
      kanun_ad: 'KVK', source_text: '',
    }))).toBe(true)
  })

  it('rejects a reference with neither kanun_no nor kanun_ad', () => {
    expect(isValidTrainingReference(ref({
      madde: '5', source_text: 'has body',
    }))).toBe(false)
  })

  it('rejects whitespace-only kanun_no AND kanun_ad', () => {
    expect(isValidTrainingReference(ref({
      kanun_no: '   ', kanun_ad: '\t', source_text: '',
    }))).toBe(false)
  })
})

describe('areAllTrainingReferencesValid', () => {
  it('accepts an empty list', () => {
    expect(areAllTrainingReferencesValid([])).toBe(true)
  })

  it('rejects when one ref is invalid', () => {
    expect(areAllTrainingReferencesValid([
      ref({ kanun_no: '5520', source_text: '' }),
      ref({ madde: '5', source_text: '' }), // no kanun_*
    ])).toBe(false)
  })
})

describe('parseComplexMadde', () => {
  it('parses full complex reference correctly', () => {
    expect(parseComplexMadde('5/1-a')).toEqual({
      madde: '5',
      fikra: '1',
      bent: 'a',
    })
  })

  it('parses Roman numerals correctly', () => {
    expect(parseComplexMadde('V/1-a')).toEqual({
      madde: 'V',
      fikra: '1',
      bent: 'a',
    })
  })

  it('parses madde and fikra only', () => {
    expect(parseComplexMadde('5/1')).toEqual({
      madde: '5',
      fikra: '1',
      bent: null,
    })
  })

  it('parses madde and bent only', () => {
    expect(parseComplexMadde('5-a')).toEqual({
      madde: '5',
      fikra: null,
      bent: 'a',
    })
  })

  it('returns null for simple madde', () => {
    expect(parseComplexMadde('5')).toBeNull()
  })

  it('returns null for invalid format', () => {
    expect(parseComplexMadde('5/1/a-b')).toBeNull()
  })
})

describe('normalizeTurkishKey', () => {
  it('normalizes Turkish characters to uppercase ascii alphanumeric keys', () => {
    expect(normalizeTurkishKey('ıİğĞüÜşŞöÖçÇ')).toBe('IIGGUUSSOOCC')
  })
})

describe('normalizeKanunAdi', () => {
  it('expands known law name abbreviations', () => {
    expect(normalizeKanunAdi('KVK')).toBe('Kurumlar Vergisi Kanunu')
    expect(normalizeKanunAdi('GVK')).toBe('Gelir Vergisi Kanunu')
    expect(normalizeKanunAdi('VUK')).toBe('Vergi Usul Kanunu')
  })
  it('returns raw text if unknown name', () => {
    expect(normalizeKanunAdi('Özel Kanun')).toBe('Özel Kanun')
    expect(normalizeKanunAdi(null)).toBeNull()
  })
})

describe('normalizeIdentifier', () => {
  it('normalizes verbal Turkish ordinal words', () => {
    expect(normalizeIdentifier('birinci')).toBe('1')
    expect(normalizeIdentifier('ikinci')).toBe('2')
  })
  it('cleans parentheses and brackets', () => {
    expect(normalizeIdentifier('(a)')).toBe('a')
    expect(normalizeIdentifier('[b]')).toBe('b')
    expect(normalizeIdentifier('c.')).toBe('c')
  })
  it('returns null for empty strings', () => {
    expect(normalizeIdentifier('')).toBeNull()
  })
})

describe('parseComplexMadde', () => {
  it('splits complex madde formats correctly', () => {
    expect(parseComplexMadde('16/1-a')).toEqual({
      madde: '16',
      fikra: '1',
      bent: 'a',
    })
    expect(parseComplexMadde('5-a')).toEqual({
      madde: '5',
      fikra: null,
      bent: 'a',
    })
    expect(parseComplexMadde('13/a')).toEqual({
      madde: '13',
      fikra: null,
      bent: 'a',
    })
  })
})
