import { formatDistance } from 'date-fns'
import { tr } from 'date-fns/locale'

export function formatRelativeTr(input: string | null | undefined): string {
  if (!input) return '-'
  const d = new Date(input)
  if (Number.isNaN(d.getTime())) return '-'
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  if (diffMs < 60_000 && diffMs >= 0) return 'az önce'
  return formatDistance(d, now, { addSuffix: true, locale: tr })
}
