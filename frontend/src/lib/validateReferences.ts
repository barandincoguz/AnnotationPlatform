import type { components } from '@/api/types'

type ReferenceItem = components['schemas']['ReferenceItem']
interface ReferenceLike {
  kanun_no?: string | null | undefined
  kanun_ad?: string | null | undefined
  madde?: string | null | undefined
  fikra?: string | null | undefined
  bent?: string | null | undefined
  source_text?: string | null | undefined
}
export type ReferenceField = 'kanun_no' | 'kanun_ad' | 'madde' | 'fikra' | 'bent'

export interface ReferenceFieldDiagnostic {
  level: 'warning' | 'error'
  message: string
  normalizedPreview?: string
}

export interface ParsedReference {
  madde: string | null
  fikra: string | null
  bent: string | null
}

const ORDINAL_MAP: Record<string, string> = {
  birinci: '1',
  ikinci: '2',
  ucuncu: '3',
  dorduncu: '4',
  besinci: '5',
  altinci: '6',
  yedinci: '7',
  sekizinci: '8',
  dokuzuncu: '9',
  onuncu: '10',
}

const LAW_ABBREVIATIONS: Record<string, string> = {
  VUK: 'Vergi Usul Kanunu',
  GVK: 'Gelir Vergisi Kanunu',
  KDVK: 'Katma Değer Vergisi Kanunu',
  KDV: 'Katma Değer Vergisi Kanunu',
  KVK: 'Kurumlar Vergisi Kanunu',
  OTVK: 'Özel Tüketim Vergisi Kanunu',
  OTV: 'Özel Tüketim Vergisi Kanunu',
  DVK: 'Damga Vergisi Kanunu',
  HK: 'Harçlar Kanunu',
  AATUHK: 'Amme Alacaklarının Tahsil Usulü Hakkında Kanun',
  AATUK: 'Amme Alacaklarının Tahsil Usulü Hakkında Kanun',
  MTVK: 'Motorlu Taşıtlar Vergisi Kanunu',
  MTV: 'Motorlu Taşıtlar Vergisi Kanunu',
  BGK: 'Belediye Gelirleri Kanunu',
  GK: 'Gümrük Kanunu',
  EVK: 'Emlak Vergisi Kanunu',
  GIVK: 'Gider Vergileri Kanunu',
  GIV: 'Gider Vergileri Kanunu',
  VIVK: 'Veraset ve İntikal Vergisi Kanunu',
  VIV: 'Veraset ve İntikal Vergisi Kanunu',
  KVKK: 'Kişisel Verilerin Korunması Kanunu',
  SBK: 'Serbest Bölgeler Kanunu',
  TGBK: 'Teknoloji Geliştirme Bölgeleri Kanunu',
  SSGSSK: 'Sosyal Sigortalar ve Genel Sağlık Sigortası Kanunu',
  SGK: 'Sosyal Sigortalar ve Genel Sağlık Sigortası Kanunu',
  IK: 'İş Kanunu',
  TTK: 'Türk Ticaret Kanunu',
  TMK: 'Türk Medeni Kanunu',
  TBK: 'Türk Borçlar Kanunu',
  HMK: 'Hukuk Muhakemeleri Kanunu',
  CMK: 'Ceza Muhakemesi Kanunu',
  TCK: 'Türk Ceza Kanunu',
  IIK: 'İcra ve İflas Kanunu',
  DMK: 'Devlet Memurları Kanunu',
  IYUK: 'İdari Yargılama Usulü Kanunu',
  IYK: 'İdari Yargılama Usulü Kanunu',
}

const LAW_NAME_ALIASES: Record<string, string> = {
  VERGIUSULKANUNU: 'Vergi Usul Kanunu',
  VERGIUSUL: 'Vergi Usul Kanunu',
  VUKKANUNU: 'Vergi Usul Kanunu',
  GELIRVERGISIKANUNU: 'Gelir Vergisi Kanunu',
  GELIRVERGISI: 'Gelir Vergisi Kanunu',
  GVKKANUNU: 'Gelir Vergisi Kanunu',
  KURUMLARVERGISIKANUNU: 'Kurumlar Vergisi Kanunu',
  KURUMLARVERGISI: 'Kurumlar Vergisi Kanunu',
  KVKKANUNU: 'Kurumlar Vergisi Kanunu',
  KATMADEGERVERGISIKANUNU: 'Katma Değer Vergisi Kanunu',
  KATMADEGERVERGISI: 'Katma Değer Vergisi Kanunu',
  KATMADEGERVERGISIKDVKANUNU: 'Katma Değer Vergisi Kanunu',
  KDVKANUNU: 'Katma Değer Vergisi Kanunu',
  KDVKANUN: 'Katma Değer Vergisi Kanunu',
  OZELTUKETIMVERGISIKANUNU: 'Özel Tüketim Vergisi Kanunu',
  OZELTUKETIMVERGISI: 'Özel Tüketim Vergisi Kanunu',
  OTVKANUNU: 'Özel Tüketim Vergisi Kanunu',
  DAMGAVERGISIKANUNU: 'Damga Vergisi Kanunu',
  DAMGAVERGISI: 'Damga Vergisi Kanunu',
  DVKKANUNU: 'Damga Vergisi Kanunu',
  HARCLARKANUNU: 'Harçlar Kanunu',
  HARCLAR: 'Harçlar Kanunu',
  HKKANUNU: 'Harçlar Kanunu',
  AMMEALACAKLARININTAHSILUSULUHAKKINDAKANUN: 'Amme Alacaklarının Tahsil Usulü Hakkında Kanun',
  AMMEALACAKLARININTAHSILUSULUHAKKINDAKANUNU: 'Amme Alacaklarının Tahsil Usulü Hakkında Kanun',
  AMMEALACAKLARININTAHSILUSULU: 'Amme Alacaklarının Tahsil Usulü Hakkında Kanun',
  AATUHKKANUNU: 'Amme Alacaklarının Tahsil Usulü Hakkında Kanun',
  AATUKKANUNU: 'Amme Alacaklarının Tahsil Usulü Hakkında Kanun',
  MOTORLUTASITLARVERGISIKANUNU: 'Motorlu Taşıtlar Vergisi Kanunu',
  MOTORLUTASITLARVERGISI: 'Motorlu Taşıtlar Vergisi Kanunu',
  MTVKANUNU: 'Motorlu Taşıtlar Vergisi Kanunu',
  MTVKKANUNU: 'Motorlu Taşıtlar Vergisi Kanunu',
  BELEDIYEGELIRLERIKANUNU: 'Belediye Gelirleri Kanunu',
  BELEDIYEGELIRLERI: 'Belediye Gelirleri Kanunu',
  BGKKANUNU: 'Belediye Gelirleri Kanunu',
  GUMRUKKANUNU: 'Gümrük Kanunu',
  GUMRUK: 'Gümrük Kanunu',
  GKKANUNU: 'Gümrük Kanunu',
  EMLAKVERGISIKANUNU: 'Emlak Vergisi Kanunu',
  EMLAKVERGISI: 'Emlak Vergisi Kanunu',
  EVKKANUNU: 'Emlak Vergisi Kanunu',
  GIDERVERGILERIKANUNU: 'Gider Vergileri Kanunu',
  GIDERVERGILERI: 'Gider Vergileri Kanunu',
  GIVKKANUNU: 'Gider Vergileri Kanunu',
  VERASETVEINTIKALVERGISIKANUNU: 'Veraset ve İntikal Vergisi Kanunu',
  VERASETVEINTIKALVERGISI: 'Veraset ve İntikal Vergisi Kanunu',
  VIVKKANUNU: 'Veraset ve İntikal Vergisi Kanunu',
  KISISELVERILERINKORUNMASIKANUNU: 'Kişisel Verilerin Korunması Kanunu',
  KISISELVERILERINKORUNMASI: 'Kişisel Verilerin Korunması Kanunu',
  KVKKKANUNU: 'Kişisel Verilerin Korunması Kanunu',
  SERBESTBOLGELERKANUNU: 'Serbest Bölgeler Kanunu',
  SERBESTBOLGELER: 'Serbest Bölgeler Kanunu',
  SBKKANUNU: 'Serbest Bölgeler Kanunu',
  TEKNOLOJIGELISTIRMEBOLGELERIKANUNU: 'Teknoloji Geliştirme Bölgeleri Kanunu',
  TEKNOLOJIGELISTIRMEBOLGELERI: 'Teknoloji Geliştirme Bölgeleri Kanunu',
  TGBKKANUNU: 'Teknoloji Geliştirme Bölgeleri Kanunu',
  SOSYALSIGORTALARVEGENELSAGLIKSIGORTASIKANUNU: 'Sosyal Sigortalar ve Genel Sağlık Sigortası Kanunu',
  SOSYALSIGORTALARVEGENELSAGLIKSIGORTASI: 'Sosyal Sigortalar ve Genel Sağlık Sigortası Kanunu',
  SSGSSKKANUNU: 'Sosyal Sigortalar ve Genel Sağlık Sigortası Kanunu',
  SGKKANUNU: 'Sosyal Sigortalar ve Genel Sağlık Sigortası Kanunu',
  ISKANUNU: 'İş Kanunu',
  IS: 'İş Kanunu',
  IKKANUNU: 'İş Kanunu',
  TURKTICARETKANUNU: 'Türk Ticaret Kanunu',
  TURKTICARET: 'Türk Ticaret Kanunu',
  TTKKANUNU: 'Türk Ticaret Kanunu',
  TURKMEDENIKANUNU: 'Türk Medeni Kanunu',
  TURKMEDENI: 'Türk Medeni Kanunu',
  TMKKANUNU: 'Türk Medeni Kanunu',
  TURKBORCLARKANUNU: 'Türk Borçlar Kanunu',
  TURKBORCLAR: 'Türk Borçlar Kanunu',
  TBKKANUNU: 'Türk Borçlar Kanunu',
  HUKUKMUHAKEMELERIKANUNU: 'Hukuk Muhakemeleri Kanunu',
  HUKUKMUHAKEMELERI: 'Hukuk Muhakemeleri Kanunu',
  HMKKANUNU: 'Hukuk Muhakemeleri Kanunu',
  CEZAMUHAKEMESIKANUNU: 'Ceza Muhakemesi Kanunu',
  CEZAMUHAKEMESI: 'Ceza Muhakemesi Kanunu',
  CMKKANUNU: 'Ceza Muhakemesi Kanunu',
  TURKCEZAKANUNU: 'Türk Ceza Kanunu',
  TURKCEZA: 'Türk Ceza Kanunu',
  TCKKANUNU: 'Türk Ceza Kanunu',
  ICRAVEIFLASKANUNU: 'İcra ve İflas Kanunu',
  ICRAVEIFLAS: 'İcra ve İflas Kanunu',
  IIKKANUNU: 'İcra ve İflas Kanunu',
  DEVLETMEMURLARIKANUNU: 'Devlet Memurları Kanunu',
  DEVLETMEMURLARI: 'Devlet Memurları Kanunu',
  DMKKANUNU: 'Devlet Memurları Kanunu',
  IDARIYARGILAMAUSULUKANUNU: 'İdari Yargılama Usulü Kanunu',
  IDARIYARGILAMAUSULU: 'İdari Yargılama Usulü Kanunu',
  IYUKKANUNU: 'İdari Yargılama Usulü Kanunu',
}

const KNOWN_ABBREVIATIONS = [
  'AATUHK', 'SSGSSK', 'TGBK', 'AATUK', 'MTVK', 'GIVK', 'VIVK', 'KVKK', 'IYUK', 'KDVK', 'OTVK',
  'VUK', 'GVK', 'KDV', 'KVK', 'OTV', 'DVK', 'MTV', 'BGK', 'EVK', 'GIV', 'VIV', 'SBK', 'SGK',
  'TTK', 'TMK', 'TBK', 'HMK', 'CMK', 'TCK', 'IIK', 'DMK', 'IYK', 'HK', 'GK', 'IK'
]

export function normalizeTurkishKey(text: string): string {
  const lower = text.toLowerCase()
  const replaced = lower
    .replace(/ı/g, 'i')
    .replace(/ş/g, 's')
    .replace(/ğ/g, 'g')
    .replace(/ü/g, 'u')
    .replace(/ö/g, 'o')
    .replace(/ç/g, 'c')
  
  return replaced
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-zA-Z0-9]/g, '')
    .toUpperCase()
}

function cleanParentheses(text: string): string {
  // Remove anything inside parentheses, brackets or braces, e.g. (KVK) -> ""
  return text
    .replace(/\s*\([^()]*\)\s*/g, ' ')
    .replace(/\s*\[[^\]]*\]\s*/g, ' ')
    .replace(/\s*\{[^{}]*\}\s*/g, ' ')
}

export function normalizeKanunAdi(text: string | null): string | null {
  if (!text) return null
  
  // 1. Clean parenthetical expressions like "Kurumlar Vergisi (KVK) Kanunu" -> "Kurumlar Vergisi Kanunu"
  const cleaned = cleanParentheses(text)
  const raw = cleaned.replace(/\s+/g, ' ').trim()
  if (!raw) return null
  
  const upperKey = normalizeTurkishKey(raw)
  
  // 2. Try direct match
  if (LAW_ABBREVIATIONS[upperKey]) {
    return LAW_ABBREVIATIONS[upperKey]
  }
  if (LAW_NAME_ALIASES[upperKey]) {
    return LAW_NAME_ALIASES[upperKey]
  }
  
  // 3. Try matching abbreviation + suffix (e.g. KVK'nın -> KVKNIN -> KVK)
  const suffixPattern = /^(?:NIN|NUN|IN|UN|YA|YE|A|E|YI|YU|I|U|DA|DE|TA|TE|DAN|DEN|TAN|TEN|CA|CE|LAR|LER|LARI|LERI|LARIN|LERIN|LARINA|LERINE|LARININ|LERININ|LARINDA|LERINDE|LARINDAN|LERINDAN|LERINDEN|LARINI|LERINI|LARICA|LERICE|NU|NI|NA|NE|NDA|NDE|NDAN|NDEN|CA|CE|LA|LE)*$/
  for (const abbr of KNOWN_ABBREVIATIONS) {
    if (upperKey.startsWith(abbr)) {
      const suffix = upperKey.slice(abbr.length)
      if (suffixPattern.test(suffix)) {
        const abbrVal = LAW_ABBREVIATIONS[abbr]
        if (abbrVal) {
          return abbrVal
        }
      }
    }
  }
  
  // 4. Try matching law name ending with "KANUN..." + suffix (e.g. Kurumlar Vergisi Kanununun -> KURUMLARVERGISIKANUNUNUN -> KURUMLARVERGISIKANUNU)
  const suffixPatNonAnchored = '(?:NIN|NUN|IN|UN|YA|YE|A|E|YI|YU|I|U|DA|DE|TA|TE|DAN|DEN|TAN|TEN|CA|CE|LAR|LER|LARI|LERI|LARIN|LERIN|LARINA|LERINE|LARININ|LERININ|LARINDA|LERINDE|LARINDAN|LERINDAN|LERINDEN|LARINI|LERINI|LARICA|LERICE|NU|NI|NA|NE|NDA|NDE|NDAN|NDEN|CA|CE|LA|LE)*$'
  const replacedKey = upperKey.replace(new RegExp('KANUN' + suffixPatNonAnchored), 'KANUNU')
  if (LAW_NAME_ALIASES[replacedKey]) {
    return LAW_NAME_ALIASES[replacedKey]
  }
  
  // 5. Try matching law name base (without "KANUNU") + suffix (e.g. Kurumlar Vergisi'nde -> KURUMLARVERGISINDE -> KURUMLARVERGISI)
  for (const [aliasKey, canonical] of Object.entries(LAW_NAME_ALIASES)) {
    if (!aliasKey.endsWith('KANUNU') && !aliasKey.endsWith('KANUN')) {
      if (upperKey.startsWith(aliasKey)) {
        const suffix = upperKey.slice(aliasKey.length)
        if (suffixPattern.test(suffix)) {
          return canonical
        }
      }
    }
  }
  
  return raw
}

export function normalizeKanunNo(value: string | null): string | null {
  if (!value) return null
  const collapsed = value.replace(/\s+/g, ' ').trim()
  const cleaned = collapsed.replace(/[^0-9A-Za-z/_-]+/g, '').replace(/^[/_-]+|[/_-]+$/g, '')
  return cleaned || null
}

export function normalizeIdentifier(val: string | null): string | null {
  if (!val) return null
  const cleaned = val.replace(/^[()[\]{}.,\s'"`]+|[()[\]{}.,\s'"`]+$/g, '')
  if (cleaned === '') return null
  const key = normalizeTurkishKey(cleaned).toLowerCase()
  const ordinal = ORDINAL_MAP[key]
  if (ordinal) return ordinal
  return /\p{L}/u.test(cleaned) ? cleaned.toLowerCase() : cleaned
}

export function normalizeMadde(val: string | null): string | null {
  if (!val) return null
  let cleaned = val.trim()
  cleaned = cleaned.replace(/^madd\w*\s+/i, '')
  cleaned = cleaned.replace(/\s*madd\w*$/i, '')
  cleaned = cleaned.replace(/(?:[iıuü]nc[iıuü]|nc[iıuü])$/i, '')
  cleaned = cleaned.replace(/^[.()\s]+|[.()\s]+$/g, '')
  return cleaned.trim() || null
}

export function cleanBent(val: string | null): string | null {
  return normalizeIdentifier(val)
}

function cleanIdentifierPart(part: string): string | null {
  const value = normalizeIdentifier(part)
  if (!value || value.includes('/') || value.includes('-')) return null
  return value
}

export function parseComplexMadde(input: string): ParsedReference | null {
  const cleaned = normalizeMadde(input)
  if (!cleaned) return null
  if (!cleaned.includes('/') && !cleaned.includes('-')) {
    return null
  }
  if ((cleaned.match(/\//g) ?? []).length > 1 || (cleaned.match(/-/g) ?? []).length > 1) {
    return null
  }

  if (cleaned.includes('/')) {
    const idxSlash = cleaned.indexOf('/')
    const madde = normalizeMadde(cleaned.substring(0, idxSlash))
    const remainder = cleaned.substring(idxSlash + 1).trim()
    if (!madde || !remainder || madde.includes('-')) return null
    
    if (remainder.includes('-')) {
      const idxDash = remainder.indexOf('-')
      const first = remainder.substring(0, idxDash).trim()
      const second = remainder.substring(idxDash + 1).trim()
      if (!first || !second || !/^\d+$/.test(first)) return null
      const bent = cleanIdentifierPart(second)
      if (!bent) return null
      
      return {
        madde,
        fikra: first,
        bent,
      }
    } else if (/^\d+$/.test(remainder)) {
      return {
        madde,
        fikra: remainder,
        bent: null,
      }
    } else {
      const bent = cleanIdentifierPart(remainder)
      if (!bent) return null
      return {
        madde,
        fikra: null,
        bent,
      }
    }
  }

  const idxDash = cleaned.indexOf('-')
  const madde = normalizeMadde(cleaned.substring(0, idxDash))
  const bent = cleanIdentifierPart(cleaned.substring(idxDash + 1))
  if (!madde || !bent) return null
  return {
    madde,
    fikra: null,
    bent,
  }
}

export function isInvalidComplexMadde(input: string | null | undefined): boolean {
  const cleaned = normalizeMadde(input ?? null)
  if (!cleaned || (!cleaned.includes('/') && !cleaned.includes('-'))) return false
  return parseComplexMadde(cleaned) === null
}

function parsedReferencePreview(parsed: ParsedReference): string {
  const parts = [`Madde ${parsed.madde}`]
  if (parsed.fikra) parts.push(`Fıkra ${parsed.fikra}`)
  if (parsed.bent) parts.push(`Bent ${parsed.bent}`)
  return parts.join(', ')
}

export function getReferenceFieldDiagnostic(
  field: ReferenceField,
  value: string | null | undefined,
  _reference?: ReferenceLike,
): ReferenceFieldDiagnostic | null {
  const raw = value ?? ''
  const trimmed = raw.trim()
  if (!trimmed) return null

  if (field === 'madde') {
    const parsed = parseComplexMadde(trimmed)
    if (parsed) {
      const preview = parsedReferencePreview(parsed)
      return {
        level: 'warning',
        message: `Kaydedilirken ${preview} olarak ayrılacak.`,
        normalizedPreview: preview,
      }
    }
    if (isInvalidComplexMadde(trimmed)) {
      return {
        level: 'error',
        message: 'Madde formatı belirsiz. Örn: 17/5-a.',
      }
    }
    const normalized = normalizeMadde(trimmed)
    if (normalized && normalized !== trimmed) {
      return {
        level: 'warning',
        message: `Kaydedilirken ${normalized} olarak düzeltilecek.`,
        normalizedPreview: normalized,
      }
    }
    return null
  }

  if (field === 'fikra' || field === 'bent') {
    const normalized = normalizeIdentifier(trimmed)
    if (normalized && normalized !== trimmed) {
      return {
        level: 'warning',
        message: `Kaydedilirken ${normalized} olarak düzeltilecek.`,
        normalizedPreview: normalized,
      }
    }
    return null
  }

  if (field === 'kanun_ad') {
    const normalized = normalizeKanunAdi(trimmed)
    if (normalized && normalized !== trimmed) {
      return {
        level: 'warning',
        message: `Kaydedilirken ${normalized} olarak düzeltilecek.`,
        normalizedPreview: normalized,
      }
    }
    return null
  }

  const normalized = normalizeKanunNo(trimmed)
  if (normalized && normalized !== trimmed) {
    return {
      level: 'warning',
      message: `Kaydedilirken ${normalized} olarak düzeltilecek.`,
      normalizedPreview: normalized,
    }
  }
  return null
}

export function emptyReferenceItem(): ReferenceItem {
  return {
    kanun_no: null,
    kanun_ad: null,
    madde: null,
    fikra: null,
    bent: null,
    source_text: '',
  }
}

function hasAtLeastOneKanunField(r: ReferenceLike): boolean {
  const hasKanunNo = (r.kanun_no?.trim() ?? '') !== ''
  const hasKanunAd = (r.kanun_ad?.trim() ?? '') !== ''
  return hasKanunNo || hasKanunAd
}

export function isValidReference(r: ReferenceLike): boolean {
  if (!r.source_text || r.source_text.trim().length === 0) return false
  if (isInvalidComplexMadde(r.madde)) return false
  return hasAtLeastOneKanunField(r)
}

export function areAllReferencesValid(refs: ReferenceItem[]): boolean {
  return refs.every(isValidReference)
}

export function isValidTrainingReference(r: ReferenceLike): boolean {
  return hasAtLeastOneKanunField(r) && !isInvalidComplexMadde(r.madde)
}

export function areAllTrainingReferencesValid(refs: ReferenceItem[]): boolean {
  return refs.every(isValidTrainingReference)
}

// --- Verbatim quote grounding ------------------------------------------
//
// This block MUST stay behaviourally identical to the downstream DQCheck gate,
// `data_quality_checker.text.evidence_match_mode`
// (ner-project/data-quality-checker-weak-learning-program/src/data_quality_checker/text.py).
// A quote the annotator saves here is later re-checked by that gate; if the two
// disagree, the annotator is told the quote is fine and the pipeline rejects it
// much later, with nobody watching.
//
// History: the previous rule accepted a quote when >= 80% of its words appeared
// ANYWHERE in the document. That was intended as typo tolerance, but it also
// accepted quotes reassembled from non-adjacent fragments -- typically a shared
// lead-in ("3065 sayili KDV Kanununun;") re-prefixed onto each item of a list of
// articles. Measured over the 1,294-document neon_wl_v1 batch, 563 of 6,098
// human quotes (9.2%) were not contiguous in their document, and the old rule
// stayed silent for 98.4% of them. See
// ner-project/Journal/evidence/findings/2026-08-24_human_evidence_grounding_gap.md
//
// Contract: a quote is grounded only if it occurs as ONE CONTIGUOUS SPAN under
// one of three escalating normalizations.

const HTML_ENTITIES: Record<string, string> = {
  amp: '&',
  lt: '<',
  gt: '>',
  quot: '"',
  apos: "'",
  nbsp: '\u00a0',
}

function unescapeHtml(input: string): string {
  return input.replace(/&(#x?[0-9a-fA-F]+|[a-zA-Z]+);/g, (match, body: string) => {
    if (body.startsWith('#')) {
      const hex = body[1] === 'x' || body[1] === 'X'
      const code = Number.parseInt(hex ? body.slice(2) : body.slice(1), hex ? 16 : 10)
      return Number.isFinite(code) && code > 0 ? String.fromCodePoint(code) : match
    }
    return HTML_ENTITIES[body.toLowerCase()] ?? match
  })
}

/** Mirrors `data_quality_checker.text.normalize_text`. */
export function normalizeQuoteText(value: string | null | undefined): string {
  return unescapeHtml(String(value ?? ''))
    .normalize('NFKC')
    .replace(/[\u00ad\u200b]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

const TYPOGRAPHIC_PUNCTUATION: Record<string, string> = {
  '\u201c': '"',
  '\u201d': '"',
  '\u2018': "'",
  '\u2019': "'",
  '\u2013': '-',
  '\u2014': '-',
}

/** Mirrors `data_quality_checker.text.folded_text`. */
function foldedQuoteText(value: string | null | undefined): string {
  return normalizeQuoteText(value)
    .toLowerCase()
    .replace(/[\u201c\u201d\u2018\u2019\u2013\u2014]/g, (c) => TYPOGRAPHIC_PUNCTUATION[c] ?? c)
}

// Mirrors data_quality_checker.text._LOOSE_RE (Turkish lowercase alphabet).
const NON_ALPHANUMERIC = /[^0-9a-zçğıöşü]+/g

/** Mirrors `data_quality_checker.text.loose_text`. */
function looseQuoteText(value: string | null | undefined): string {
  return foldedQuoteText(value).replace(NON_ALPHANUMERIC, ' ').trim()
}

export type QuoteGroundingMode =
  | 'normalized_exact'
  | 'case_punctuation_normalized'
  | 'loose_alphanumeric'

/**
 * Mirrors `data_quality_checker.text.evidence_match_mode`: returns the weakest
 * normalization at which the quote is a contiguous substring of the document,
 * or `null` when it is not grounded at all.
 */
export function quoteGroundingMode(
  sourceText: string | null | undefined,
  docText: string | null | undefined,
): QuoteGroundingMode | null {
  const source = normalizeQuoteText(sourceText)
  if (!source) return null
  const doc = String(docText ?? '')
  if (doc.includes(source)) return 'normalized_exact'
  if (foldedQuoteText(doc).includes(foldedQuoteText(source))) {
    return 'case_punctuation_normalized'
  }
  const looseSource = looseQuoteText(source)
  if (looseSource && looseQuoteText(doc).includes(looseSource)) {
    return 'loose_alphanumeric'
  }
  return null
}

export function isSourceTextInDoc(
  sourceText: string | null | undefined,
  docText: string | null | undefined,
): boolean {
  if (!sourceText?.trim()) return true
  if (!docText) return false
  return quoteGroundingMode(sourceText, docText) !== null
}

export function isReferenceBlank(r: ReferenceLike): boolean {
  return (
    !(r.kanun_no?.trim()) &&
    !(r.kanun_ad?.trim()) &&
    !(r.madde?.trim()) &&
    !(r.fikra?.trim()) &&
    !(r.bent?.trim())
  )
}

export function areReferencesEquivalent(r1: ReferenceLike, r2: ReferenceLike): boolean {
  const no1 = normalizeKanunNo(r1.kanun_no ?? null)
  const no2 = normalizeKanunNo(r2.kanun_no ?? null)
  const ad1 = normalizeKanunAdi(r1.kanun_ad ?? null)
  const ad2 = normalizeKanunAdi(r2.kanun_ad ?? null)
  const m1 = normalizeMadde(r1.madde ?? null)
  const m2 = normalizeMadde(r2.madde ?? null)
  const f1 = normalizeIdentifier(r1.fikra ?? null)
  const f2 = normalizeIdentifier(r2.fikra ?? null)
  const b1 = normalizeIdentifier(r1.bent ?? null)
  const b2 = normalizeIdentifier(r2.bent ?? null)

  return no1 === no2 && ad1 === ad2 && m1 === m2 && f1 === f2 && b1 === b2
}

export function checkAndRemoveDuplicateReferences(
  refs: ReferenceItem[],
): { list: ReferenceItem[]; hasDuplicates: boolean } {
  const result: ReferenceItem[] = []
  let hasDuplicates = false

  for (const r of refs) {
    if (isReferenceBlank(r)) {
      result.push(r)
      continue
    }

    const isDuplicate = result.some((existing) => {
      if (isReferenceBlank(existing)) return false
      return areReferencesEquivalent(r, existing)
    })

    if (isDuplicate) {
      hasDuplicates = true
    } else {
      result.push(r)
    }
  }

  return { list: result, hasDuplicates }
}

export const LAW_NAME_BY_NUMBER: Record<string, string> = {
  '213': 'Vergi Usul Kanunu',
  '193': 'Gelir Vergisi Kanunu',
  '5520': 'Kurumlar Vergisi Kanunu',
  '3065': 'Katma Değer Vergisi Kanunu',
  '4760': 'Özel Tüketim Vergisi Kanunu',
  '488': 'Damga Vergisi Kanunu',
  '492': 'Harçlar Kanunu',
  '6183': 'Amme Alacaklarının Tahsil Usulü Hakkında Kanun',
  '197': 'Motorlu Taşıtlar Vergisi Kanunu',
  '2464': 'Belediye Gelirleri Kanunu',
  '4458': 'Gümrük Kanunu',
  '1319': 'Emlak Vergisi Kanunu',
  '6802': 'Gider Vergileri Kanunu',
  '7338': 'Veraset ve İntikal Vergisi Kanunu',
  '6698': 'Kişisel Verilerin Korunması Kanunu',
  '3218': 'Serbest Bölgeler Kanunu',
  '4691': 'Teknoloji Geliştirme Bölgeleri Kanunu',
  '5510': 'Sosyal Sigortalar ve Genel Sağlık Sigortası Kanunu',
  '4857': 'İş Kanunu',
  '6102': 'Türk Ticaret Kanunu',
  '4721': 'Türk Medeni Kanunu',
  '6098': 'Türk Borçlar Kanunu',
  '6100': 'Hukuk Muhakemeleri Kanunu',
  '5271': 'Ceza Muhakemesi Kanunu',
  '5237': 'Türk Ceza Kanunu',
  '2004': 'İcra ve İflas Kanunu',
  '657': 'Devlet Memurları Kanunu',
  '2577': 'İdari Yargılama Usulü Kanunu',
}

export const LAW_NUMBER_BY_NAME: Record<string, string> = {
  'Vergi Usul Kanunu': '213',
  'Gelir Vergisi Kanunu': '193',
  'Kurumlar Vergisi Kanunu': '5520',
  'Katma Değer Vergisi Kanunu': '3065',
  'Özel Tüketim Vergisi Kanunu': '4760',
  'Damga Vergisi Kanunu': '488',
  'Harçlar Kanunu': '492',
  'Amme Alacaklarının Tahsil Usulü Hakkında Kanun': '6183',
  'Motorlu Taşıtlar Vergisi Kanunu': '197',
  'Belediye Gelirleri Kanunu': '2464',
  'Gümrük Kanunu': '4458',
  'Emlak Vergisi Kanunu': '1319',
  'Gider Vergileri Kanunu': '6802',
  'Veraset ve İntikal Vergisi Kanunu': '7338',
  'Kişisel Verilerin Korunması Kanunu': '6698',
  'Serbest Bölgeler Kanunu': '3218',
  'Teknoloji Geliştirme Bölgeleri Kanunu': '4691',
  'Sosyal Sigortalar ve Genel Sağlık Sigortası Kanunu': '5510',
  'İş Kanunu': '4857',
  'Türk Ticaret Kanunu': '6102',
  'Türk Medeni Kanunu': '4721',
  'Türk Borçlar Kanunu': '6098',
  'Hukuk Muhakemeleri Kanunu': '6100',
  'Ceza Muhakemesi Kanunu': '5271',
  'Türk Ceza Kanunu': '5237',
  'İcra ve İflas Kanunu': '2004',
  'Devlet Memurları Kanunu': '657',
  'İdari Yargılama Usulü Kanunu': '2577',
}

export function getLawNameByNumber(num: string | null | undefined): string | null {
  if (!num) return null
  const cleaned = normalizeKanunNo(num)
  return cleaned ? (LAW_NAME_BY_NUMBER[cleaned] ?? null) : null
}

export function getLawNumberByName(name: string | null | undefined): string | null {
  if (!name) return null
  const cleaned = normalizeKanunAdi(name)
  return cleaned ? (LAW_NUMBER_BY_NAME[cleaned] ?? null) : null
}
