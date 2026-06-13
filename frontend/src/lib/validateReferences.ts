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
}

const LAW_NAME_ALIASES: Record<string, string> = {
  VERGIUSULKANUNU: 'Vergi Usul Kanunu',
  VUKKANUNU: 'Vergi Usul Kanunu',
  GELIRVERGISIKANUNU: 'Gelir Vergisi Kanunu',
  GVKKANUNU: 'Gelir Vergisi Kanunu',
  KURUMLARVERGISIKANUNU: 'Kurumlar Vergisi Kanunu',
  KVKKANUNU: 'Kurumlar Vergisi Kanunu',
  KATMADEGERVERGISIKANUNU: 'Katma Değer Vergisi Kanunu',
  KATMADEGERVERGISIKDVKANUNU: 'Katma Değer Vergisi Kanunu',
  KDVKANUNU: 'Katma Değer Vergisi Kanunu',
  OZELTUKETIMVERGISIKANUNU: 'Özel Tüketim Vergisi Kanunu',
  OTVKANUNU: 'Özel Tüketim Vergisi Kanunu',
  DAMGAVERGISIKANUNU: 'Damga Vergisi Kanunu',
  DVKKANUNU: 'Damga Vergisi Kanunu',
  HARCLARKANUNU: 'Harçlar Kanunu',
}

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

export function normalizeKanunAdi(text: string | null): string | null {
  if (!text) return null
  const trimmed = text.trim()
  const upperKey = normalizeTurkishKey(trimmed)
  if (LAW_ABBREVIATIONS[upperKey]) {
    return LAW_ABBREVIATIONS[upperKey]
  }
  if (LAW_NAME_ALIASES[upperKey]) {
    return LAW_NAME_ALIASES[upperKey]
  }
  return trimmed || null
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
