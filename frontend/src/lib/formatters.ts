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

/**
 * Format a backend YYYYMMDD date string (e.g. "20260123" coming from
 * the source özelge JSON) as Turkish dd.mm.yyyy.
 *
 * Returns the original string unchanged if it doesn't match the
 * expected 8-digit numeric shape — defensive against the few rows in
 * the dataset where vergi_turu / tarih got swapped during ingestion.
 */
export function formatYmd(input: string | null | undefined): string {
  if (!input) return '—'
  const trimmed = input.trim()
  if (!/^\d{8}$/.test(trimmed)) return trimmed
  const year = trimmed.slice(0, 4)
  const month = trimmed.slice(4, 6)
  const day = trimmed.slice(6, 8)
  return `${day}.${month}.${year}`
}
