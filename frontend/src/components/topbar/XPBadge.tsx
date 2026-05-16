const TR_FORMATTER = new Intl.NumberFormat('tr-TR')

interface XPBadgeProps {
  total: number
}

export function XPBadge({ total }: XPBadgeProps) {
  return (
    <span
      aria-label="Toplam XP"
      className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-0.5 shadow-sm"
    >
      <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-muted-foreground">XP</span>
      <span className="font-display text-sm font-medium tabular-nums">{TR_FORMATTER.format(total)}</span>
    </span>
  )
}
