import type { components } from '@/api/types'

type ReferenceItem = components['schemas']['ReferenceItem']

/**
 * Canonical empty-row factory. Two earlier sites built this literal by
 * hand (useReferencesState's `empty()` and training's `emptyRef()`);
 * consolidated here so adding a new optional field touches one place.
 */
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

/**
 * True iff the reference has SOME kanun signal (kanun_no or kanun_ad).
 * Shared helper that both validators below call — the same three lines
 * were duplicated in `isValidReference` and `isValidTrainingReference`.
 */
function hasAtLeastOneKanunField(r: ReferenceItem): boolean {
  const hasKanunNo = (r.kanun_no?.trim() ?? '') !== ''
  const hasKanunAd = (r.kanun_ad?.trim() ?? '') !== ''
  return hasKanunNo || hasKanunAd
}

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
  return hasAtLeastOneKanunField(r)
}

/**
 * The full references list is valid iff every reference is individually
 * valid. An empty list passes (zero-ref is the legal "no law citations
 * apply" case — backend handles it).
 */
export function areAllReferencesValid(refs: ReferenceItem[]): boolean {
  return refs.every(isValidReference)
}

/**
 * 16c.1 training-variant validator: source_text is optional because the
 * backend matcher ignores it anyway. Still requires at least one of
 * {kanun_no, kanun_ad} so the reference is meaningful for concept
 * matching. The strict isValidReference above stays in force for 16b
 * main annotation save — do NOT swap it.
 */
export function isValidTrainingReference(r: ReferenceItem): boolean {
  return hasAtLeastOneKanunField(r)
}

export function areAllTrainingReferencesValid(refs: ReferenceItem[]): boolean {
  return refs.every(isValidTrainingReference)
}
