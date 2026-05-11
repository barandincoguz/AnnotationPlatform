const REQUIRED_KEYS = ['kanun_no', 'kanun_ad', 'madde'] as const
const OPTIONAL_KEYS = ['fikra', 'bent'] as const

/**
 * Format a single training concept dict as human-readable text for
 * the AnnotateStep reveal panel. Required keys (kanun_no, kanun_ad,
 * madde) appear first comma-separated; optional keys (fikra, bent)
 * appear afterwards in parentheses. Empty / null / undefined values
 * are omitted.
 *
 * Example: { kanun_no: '5520', madde: '5', fikra: '1', bent: 'a' }
 *   → "kanun_no: 5520, madde: 5 (fikra: 1) (bent: a)"
 */
export function formatConcept(
  c: Record<string, string | null | undefined>,
): string {
  const required = REQUIRED_KEYS
    .filter((k) => c[k])
    .map((k) => `${k}: ${c[k]}`)
    .join(', ')
  const optional = OPTIONAL_KEYS
    .filter((k) => c[k])
    .map((k) => `(${k}: ${c[k]})`)
    .join(' ')
  return [required, optional].filter(Boolean).join(' ')
}
