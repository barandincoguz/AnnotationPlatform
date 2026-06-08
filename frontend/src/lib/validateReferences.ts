import type { components } from '@/api/types'

type ReferenceItem = components['schemas']['ReferenceItem']

export interface ParsedReference {
  madde: string | null
  fikra: string | null
  bent: string | null
}

/**
 * Parses a complex madde input (e.g., "5/1-a") into separate fields.
 */
export function parseComplexMadde(input: string): ParsedReference | null {
  const trimmed = input.trim()
  if (!trimmed) return null
  
  if (!trimmed.includes('/') && !trimmed.includes('-')) {
    return null
  }
  
  const match = trimmed.match(/^([0-9a-zA-Z]+)(?:\/([0-9a-zA-Z]+))?(?:-([a-zA-ZçğıöşüÇĞİÖŞÜ]+))?$/)
  if (!match) {
    return null
  }
  
  return {
    madde: match[1] || null,
    fikra: match[2] || null,
    bent: match[3] || null,
  }
}

/**
 * Cleans the bent field by stripping parentheses, dots, quotes, and converting to lowercase.
 */
export function cleanBent(val: string | null): string | null {
  if (!val) return null
  const cleaned = val.replace(/^[().'"\s]+|[().'"\s]+$/g, '').toLowerCase()
  return cleaned || null
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
