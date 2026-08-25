import { describe, it, expect } from 'vitest'
import {
  isValidReference, areAllReferencesValid,
  isValidTrainingReference, areAllTrainingReferencesValid,
  parseComplexMadde,
  normalizeTurkishKey, normalizeKanunAdi, normalizeIdentifier,
  normalizeKanunNo, normalizeMadde,
  isInvalidComplexMadde,
  getReferenceFieldDiagnostic,
  isSourceTextInDoc,
  quoteGroundingMode,
  checkAndRemoveDuplicateReferences,
  getLawNameByNumber,
  getLawNumberByName,
} from './validateReferences'
import type { QuoteGroundingMode } from './validateReferences'

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

  it('accepts parseable complex madde but rejects ambiguous complex madde', () => {
    expect(isValidReference(ref({ kanun_no: '5520', madde: '17/5-a', source_text: 'metin' }))).toBe(true)
    expect(isValidReference(ref({ kanun_no: '5520', madde: '17--a', source_text: 'metin' }))).toBe(false)
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

  it('accepts parseable complex madde but rejects ambiguous complex madde', () => {
    expect(isValidTrainingReference(ref({
      kanun_no: '5520', madde: '17/5-a', source_text: '',
    }))).toBe(true)
    expect(isValidTrainingReference(ref({
      kanun_no: '5520', madde: '17--a', source_text: '',
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
    expect(parseComplexMadde('16/1-a')).toEqual({
      madde: '16',
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
    expect(parseComplexMadde('13/a')).toEqual({
      madde: '13',
      fikra: null,
      bent: 'a',
    })
  })

  it('returns null for simple madde', () => {
    expect(parseComplexMadde('5')).toBeNull()
  })

  it('returns null for invalid format', () => {
    expect(parseComplexMadde('5/1/a-b')).toBeNull()
    expect(parseComplexMadde('17--a')).toBeNull()
    expect(parseComplexMadde('/5-a')).toBeNull()
    expect(parseComplexMadde('17/-a')).toBeNull()
    expect(isInvalidComplexMadde('17--a')).toBe(true)
    expect(isInvalidComplexMadde('17/5-a')).toBe(false)
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
  it('normalizes laws with Turkish suffixes and parentheticals', () => {
    // Parenthetical removal
    expect(normalizeKanunAdi('Kurumlar Vergisi (KVK) Kanunu')).toBe('Kurumlar Vergisi Kanunu')
    expect(normalizeKanunAdi('Kurumlar Vergisi (KVK) Kanununun')).toBe('Kurumlar Vergisi Kanunu')
    
    // Abbreviation suffixes
    expect(normalizeKanunAdi("KVK'nın")).toBe('Kurumlar Vergisi Kanunu')
    expect(normalizeKanunAdi("GVK'ya")).toBe('Gelir Vergisi Kanunu')
    expect(normalizeKanunAdi("VUK'un")).toBe('Vergi Usul Kanunu')
    expect(normalizeKanunAdi("KDVK'nın")).toBe('Katma Değer Vergisi Kanunu')
    
    // Law name suffixes
    expect(normalizeKanunAdi("Kurumlar Vergisi Kanunu'na")).toBe('Kurumlar Vergisi Kanunu')
    expect(normalizeKanunAdi("Kurumlar Vergisi Kanunundan")).toBe('Kurumlar Vergisi Kanunu')
    
    // Law base with suffix
    expect(normalizeKanunAdi("Kurumlar Vergisi'nde")).toBe('Kurumlar Vergisi Kanunu')
    
    // New laws/abbreviations
    expect(normalizeKanunAdi('TTK')).toBe('Türk Ticaret Kanunu')
    expect(normalizeKanunAdi("KVKK'ya")).toBe('Kişisel Verilerin Korunması Kanunu')
    expect(normalizeKanunAdi('AATUHK')).toBe('Amme Alacaklarının Tahsil Usulü Hakkında Kanun')
  })
  it('returns raw text if unknown name', () => {
    expect(normalizeKanunAdi('Özel Kanun')).toBe('Özel Kanun')
    expect(normalizeKanunAdi(null)).toBeNull()
  })
})

describe('normalizeKanunNo', () => {
  it('removes non identifier punctuation and trims edge separators', () => {
    expect(normalizeKanunNo(' 213. ')).toBe('213')
    expect(normalizeKanunNo('/5520-')).toBe('5520')
    expect(normalizeKanunNo(null)).toBeNull()
  })
})

describe('normalizeIdentifier', () => {
  it('normalizes verbal Turkish ordinal words', () => {
    expect(normalizeIdentifier('birinci')).toBe('1')
    expect(normalizeIdentifier('ikinci')).toBe('2')
  })
  it('cleans parentheses and brackets', () => {
    expect(normalizeIdentifier('(a)')).toBe('a')
    expect(normalizeIdentifier('(A).')).toBe('a')
    expect(normalizeIdentifier('"A"')).toBe('a')
    expect(normalizeIdentifier("'a'")).toBe('a')
    expect(normalizeIdentifier('`A`')).toBe('a')
    expect(normalizeIdentifier('[b]')).toBe('b')
    expect(normalizeIdentifier('c.')).toBe('c')
  })
  it('returns null for empty strings', () => {
    expect(normalizeIdentifier('')).toBeNull()
  })
})



describe('normalizeMadde', () => {
  it('strips madde keywords and ordinals', () => {
    expect(normalizeMadde('madde 15')).toBe('15')
    expect(normalizeMadde('15. madde')).toBe('15')
    expect(normalizeMadde('15.')).toBe('15')
    expect(normalizeMadde('(15)')).toBe('15')
  })
})

describe('getReferenceFieldDiagnostic', () => {
  it('returns a split preview for parseable complex madde', () => {
    expect(getReferenceFieldDiagnostic('madde', '17/5-a')).toEqual({
      level: 'warning',
      message: 'Kaydedilirken Madde 17, Fıkra 5, Bent a olarak ayrılacak.',
      normalizedPreview: 'Madde 17, Fıkra 5, Bent a',
    })
  })

  it('returns an error for ambiguous complex madde', () => {
    expect(getReferenceFieldDiagnostic('madde', '17--a')).toEqual({
      level: 'error',
      message: 'Madde formatı belirsiz. Örn: 17/5-a.',
    })
  })

  it('returns correction previews for identifiers and law fields', () => {
    expect(getReferenceFieldDiagnostic('bent', '(A)')?.message).toBe('Kaydedilirken a olarak düzeltilecek.')
    expect(getReferenceFieldDiagnostic('fikra', 'birinci')?.message).toBe('Kaydedilirken 1 olarak düzeltilecek.')
    expect(getReferenceFieldDiagnostic('kanun_ad', 'VUK')?.message).toBe('Kaydedilirken Vergi Usul Kanunu olarak düzeltilecek.')
    expect(getReferenceFieldDiagnostic('kanun_no', '213.')?.message).toBe('Kaydedilirken 213 olarak düzeltilecek.')
  })
})

describe('isSourceTextInDoc', () => {
  const docText = 'Kurumlar Vergisi Kanununun 5 inci maddesinin birinci fıkrasının (e) bendinde yer alan istisna hükmü.'

  it('returns true if sourceText is empty or blank', () => {
    expect(isSourceTextInDoc('', docText)).toBe(true)
    expect(isSourceTextInDoc('   ', docText)).toBe(true)
    expect(isSourceTextInDoc(null, docText)).toBe(true)
  })

  it('returns false if docText is empty but sourceText is present', () => {
    expect(isSourceTextInDoc('istisna', '')).toBe(false)
    expect(isSourceTextInDoc('istisna', null)).toBe(false)
  })

  it('returns true on a contiguous span, ignoring case, spacing and punctuation', () => {
    expect(isSourceTextInDoc('5 inci maddesinin birinci fıkrasının', docText)).toBe(true)
    // Case is folded (ASCII capitals only -- see the dotted-i test below).
    expect(isSourceTextInDoc('5 INCI MADDESININ', docText)).toBe(true)
    // Collapsed whitespace and trailing punctuation are tolerated.
    expect(isSourceTextInDoc('  5 inci   maddesinin, birinci fıkrasının  ', docText)).toBe(true)
    expect(isSourceTextInDoc('(e) bendinde yer alan istisna', docText)).toBe(true)
  })

  // Parity guard. These expectations are the verbatim output of the downstream
  // reference implementation on the same inputs:
  //   from data_quality_checker.text import evidence_match_mode
  // If this table drifts, the two gates have diverged and annotators will again
  // be told a quote is fine that the pipeline later rejects.
  it('matches evidence_match_mode mode-for-mode', () => {
    const expected: [string, QuoteGroundingMode | null][] = [
      ['5 inci maddesinin birinci fıkrasının', 'normalized_exact'],
      ['5 İNCİ MADDESİNİN BİRİNCİ FIKRASININ', null],
      ['5 INCI MADDESININ', 'case_punctuation_normalized'],
      ['KURUMLAR VERGİSİ KANUNUNUN', null],
      ['Kurumlar Vergisi Kanununun', 'normalized_exact'],
      ['  5 inci   maddesinin, birinci fıkrasının  ', 'loose_alphanumeric'],
      ['(e) bendinde yer alan istisna', 'normalized_exact'],
      ['birinci fikrasinin', null],
      ['5 inci maddesinin birinci fıkrasının yanlisword bendinde yer alan', null],
    ]
    const actual = expected.map(([source]) => [source, quoteGroundingMode(source, docText)])
    expect(actual).toEqual(expected)
  })

  // Contract change (2026-08-24): the old rule accepted a quote when >=80% of
  // its words appeared anywhere in the document. The downstream DQCheck gate
  // has no such tolerance, so accepting these here only moved the rejection
  // somewhere nobody was watching. Dotless/dotted Turkish i is likewise NOT
  // folded to ASCII, because the downstream gate does not fold it either.
  it('rejects a quote with a word that is not in the document', () => {
    const source = '5 inci maddesinin birinci fıkrasının yanlisword bendinde yer alan'
    expect(isSourceTextInDoc(source, docText)).toBe(false)
  })

  it('does not fold Turkish dotted/dotless i to ASCII', () => {
    // Document says "fıkrasının"; an ASCII "fikrasinin" is a different string
    // downstream, so it must not be reported as grounded here.
    expect(isSourceTextInDoc('birinci fikrasinin', docText)).toBe(false)
  })

  it('returns false if less than 80% of words exist in the document', () => {
    const source = 'bu cümle tamamen uydurulmuş bir cümledir hiçbir şekilde eşleşmez'
    expect(isSourceTextInDoc(source, docText)).toBe(false)
  })

  // Regression: real defect from neon_wl_v1 / d000546. A ruling lists several
  // articles under ONE shared lead-in; the annotator re-prefixed that lead-in
  // onto each list item. Every word is present in the document, so a
  // word-presence rule accepts it, but the downstream DQCheck gate
  // (evidence_match_mode) requires one contiguous span and rejects it.
  it('rejects a quote reassembled from a shared lead-in and a distant list item', () => {
    const ruling =
      '3065 sayılı KDV Kanununun; -1/1 inci maddesinde, Türkiye’de yapılan ' +
      'teslim ve hizmetlerin KDV ye tabi olduğu, -11/1-a maddesinde, serbest ' +
      'bölgelerdeki müşteriler için yapılan fason hizmetlerin KDV den istisna ' +
      'olduğu, -12/3 üncü maddesinde, fason hizmetlerin serbest bölgelerdeki ' +
      'müşterilere yapılmış sayılabilmesi gerektiği hükümleri yer almaktadır.'
    // Contiguous in the ruling -> accepted.
    expect(isSourceTextInDoc('-11/1-a maddesinde, serbest', ruling)).toBe(true)
    // Reassembled, never contiguous -> must be rejected.
    expect(isSourceTextInDoc('3065 sayılı KDV Kanununun; 11/1-a maddesinde', ruling)).toBe(false)
    expect(isSourceTextInDoc('3065 sayılı KDV Kanununun; 12/3 üncü maddesinde', ruling)).toBe(false)
  })

  it('rejects two distant spans joined with an ellipsis', () => {
    const ruling =
      '193 sayılı Gelir Vergisi Kanununun 65 inci maddesinde tanım yer alır. ' +
      'Devamla, anılan Kanunun 67 nci maddesinin birinci fıkrasında, serbest ' +
      'meslek kazancının tespiti düzenlenmiştir.'
    expect(
      isSourceTextInDoc(
        '193 sayılı Gelir Vergisi Kanununun...anılan Kanunun 67 nci maddesinin birinci fıkrasında,',
        ruling,
      ),
    ).toBe(false)
  })

  it('still accepts a contiguous quote that straddles a line break', () => {
    const wrapped = 'Kurumlar Vergisi Kanununun 5 inci\nmaddesinin birinci fıkrasının (e) bendinde'
    expect(isSourceTextInDoc('5 inci maddesinin birinci fıkrasının (e) bendinde', wrapped)).toBe(true)
  })
})

describe('checkAndRemoveDuplicateReferences', () => {
  it('does not touch unique or empty references', () => {
    const list = [
      ref({ kanun_no: '5520', madde: '5', source_text: 'first' }),
      ref({ kanun_no: '193', madde: '6', source_text: 'second' }),
      ref({ source_text: 'empty one' }),
    ]
    const { list: cleaned, hasDuplicates } = checkAndRemoveDuplicateReferences(list)
    expect(hasDuplicates).toBe(false)
    expect(cleaned).toHaveLength(3)
  })

  it('removes equivalent references ignoring source_text', () => {
    const list = [
      ref({ kanun_no: '5520', madde: '5', source_text: 'first' }),
      ref({ kanun_no: '5520', madde: '5', source_text: 'different source text' }),
      ref({ kanun_no: '5520', madde: '6', source_text: 'third' }),
    ]
    const { list: cleaned, hasDuplicates } = checkAndRemoveDuplicateReferences(list)
    expect(hasDuplicates).toBe(true)
    expect(cleaned).toHaveLength(2)
    expect(cleaned[0]?.source_text).toBe('first')
    expect(cleaned[1]?.madde).toBe('6')
  })

  it('tolerates minor formatting differences via normalization', () => {
    const list = [
      ref({ kanun_no: '5520 ', madde: 'Madde 5', source_text: 'first' }),
      ref({ kanun_no: '5520', madde: '5', source_text: 'second' }),
    ]
    const { list: cleaned, hasDuplicates } = checkAndRemoveDuplicateReferences(list)
    expect(hasDuplicates).toBe(true)
    expect(cleaned).toHaveLength(1)
  })
})

describe('auto-fill helpers', () => {
  describe('getLawNameByNumber', () => {
    it('returns the correct law name for known numbers', () => {
      expect(getLawNameByNumber('5520')).toBe('Kurumlar Vergisi Kanunu')
      expect(getLawNameByNumber(' 3065 ')).toBe('Katma Değer Vergisi Kanunu')
      expect(getLawNameByNumber('/213-')).toBe('Vergi Usul Kanunu')
    })
    it('returns null for unknown numbers', () => {
      expect(getLawNameByNumber('9999')).toBeNull()
      expect(getLawNameByNumber(null)).toBeNull()
    })
  })

  describe('getLawNumberByName', () => {
    it('returns the correct law number for known names and abbreviations', () => {
      expect(getLawNumberByName('KVK')).toBe('5520')
      expect(getLawNumberByName('Katma Değer Vergisi')).toBe('3065')
      expect(getLawNumberByName("KVK'nın")).toBe('5520')
      expect(getLawNumberByName('Kurumlar Vergisi Kanunu')).toBe('5520')
    })
    it('returns null for unknown names', () => {
      expect(getLawNumberByName('Bilinmeyen Kanun')).toBeNull()
      expect(getLawNumberByName(null)).toBeNull()
    })
  })
})

