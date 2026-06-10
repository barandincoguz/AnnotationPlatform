import type { components } from '@/api/types'

type ReferenceItem = components['schemas']['ReferenceItem']

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

export function normalizeIdentifier(val: string | null): string | null {
  if (!val) return null
  const cleaned = val.replace(/^[()[\]{}.\s,]+|[()[\]{}.\s,]+$/g, '')
  const key = normalizeTurkishKey(cleaned).toLowerCase()
  return ORDINAL_MAP[key] || cleaned || null
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

export function parseComplexMadde(input: string): ParsedReference | null {
  const cleaned = normalizeMadde(input)
  if (!cleaned) return null
  if (!cleaned.includes('/') && !cleaned.includes('-')) {
    return null
  }
  if ((cleaned.match(/\//g) || []).length > 1 || (cleaned.match(/-/g) || []).length > 1) {
    return null
  }

  if (cleaned.includes('/')) {
    // Split once at '/'
    const idxSlash = cleaned.indexOf('/')
    const madde = normalizeMadde(cleaned.substring(0, idxSlash))
    const remainder = cleaned.substring(idxSlash + 1).trim()
    
    if (remainder.includes('-')) {
      // Split once at '-'
      const idxDash = remainder.indexOf('-')
      const first = remainder.substring(0, idxDash).trim()
      const second = remainder.substring(idxDash + 1).trim()
      
      if (/^\d+$/.test(first)) {
        return {
          madde: madde,
          fikra: first,
          bent: normalizeIdentifier(second),
        }
      } else {
        return {
          madde: madde,
          fikra: null,
          bent: normalizeIdentifier(remainder),
        }
      }
    } else if (/^\d+$/.test(remainder)) {
      return {
        madde: madde,
        fikra: remainder,
        bent: null,
      }
    } else {
      return {
        madde: madde,
        fikra: null,
        bent: normalizeIdentifier(remainder),
      }
    }
  } else {
    // Split once at '-'
    const idxDash = cleaned.indexOf('-')
    return {
      madde: normalizeMadde(cleaned.substring(0, idxDash)),
      fikra: null,
      bent: normalizeIdentifier(cleaned.substring(idxDash + 1)),
    }
  }
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

function hasAtLeastOneKanunField(r: ReferenceItem): boolean {
  const hasKanunNo = (r.kanun_no?.trim() ?? '') !== ''
  const hasKanunAd = (r.kanun_ad?.trim() ?? '') !== ''
  return hasKanunNo || hasKanunAd
}

export function isValidReference(r: ReferenceItem): boolean {
  if (!r.source_text || r.source_text.trim().length === 0) return false
  if (r.madde && (r.madde.includes('/') || r.madde.includes('-'))) {
    return false
  }
  return hasAtLeastOneKanunField(r)
}

export function areAllReferencesValid(refs: ReferenceItem[]): boolean {
  return refs.every(isValidReference)
}

export function isValidTrainingReference(r: ReferenceItem): boolean {
  return hasAtLeastOneKanunField(r)
}

export function areAllTrainingReferencesValid(refs: ReferenceItem[]): boolean {
  return refs.every(isValidTrainingReference)
}
