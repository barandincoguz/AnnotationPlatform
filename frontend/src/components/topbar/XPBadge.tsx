const TR_FORMATTER = new Intl.NumberFormat('tr-TR')

interface XPBadgeProps {
  total: number
}

export function XPBadge({ total }: XPBadgeProps) {
  return (
    <span
      aria-label="Toplam XP"
      className="inline-flex items-center gap-1 text-sm font-medium"
    >
      <span aria-hidden="true">✨</span>
      <span>{TR_FORMATTER.format(total)}</span>
    </span>
  )
}
