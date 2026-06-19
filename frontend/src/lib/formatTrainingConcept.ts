const REQUIRED_KEYS = ['kanun_no', 'kanun_ad', 'madde'] as const
const OPTIONAL_KEYS = ['fikra', 'bent'] as const
const LABELS: Record<(typeof REQUIRED_KEYS)[number] | (typeof OPTIONAL_KEYS)[number], string> = {
  kanun_no: 'Kanun No',
  kanun_ad: 'Kanun Adı',
  madde: 'Madde',
  fikra: 'Fıkra',
  bent: 'Bent',
}

/**
 * Format a single training concept dict as human-readable text for
 * the AnnotateStep post-submission feedback panel. Required keys (kanun_no, kanun_ad,
 * madde) appear first comma-separated; optional keys (fikra, bent)
 * appear afterwards in parentheses. Empty / null / undefined values
 * are omitted.
 *
 * Example: { kanun_no: '5520', madde: '5', fikra: '1', bent: 'a' }
 *   -> "Kanun No: 5520, Madde: 5 (Fıkra: 1) (Bent: a)"
 */
export function formatConcept(
  c: Record<string, string | null | undefined>,
): string {
  const required = REQUIRED_KEYS
    .filter((k) => c[k])
    .map((k) => `${LABELS[k]}: ${c[k]}`)
    .join(', ')
  const optional = OPTIONAL_KEYS
    .filter((k) => c[k])
    .map((k) => `(${LABELS[k]}: ${c[k]})`)
    .join(' ')
  return [required, optional].filter(Boolean).join(' ')
}
