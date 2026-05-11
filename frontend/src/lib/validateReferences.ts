import type { components } from '@/api/types'

type ReferenceItem = components['schemas']['ReferenceItem']

/**
 * A reference is valid iff source_text is non-empty AND at least one of
 * {kanun_no, kanun_ad} is present.
 *
 * Backend Pydantic shape only requires source_text — kanun_no, kanun_ad,
 * madde, fikra, bent are all optional. This client-side rule prevents
 * users from saving useless empty references (no kanun_* → not findable
 * via concept matching, no value for downstream search).
 */
export function isValidReference(r: ReferenceItem): boolean {
  if (!r.source_text || r.source_text.trim().length === 0) return false
  const hasKanunNo = (r.kanun_no?.trim() ?? '') !== ''
  const hasKanunAd = (r.kanun_ad?.trim() ?? '') !== ''
  if (!hasKanunNo && !hasKanunAd) return false
  return true
}

/**
 * The full references list is valid iff every reference is individually
 * valid. An empty list passes (zero-ref is the legal "no law citations
 * apply" case — backend handles it).
 */
export function areAllReferencesValid(refs: ReferenceItem[]): boolean {
  return refs.every(isValidReference)
}
