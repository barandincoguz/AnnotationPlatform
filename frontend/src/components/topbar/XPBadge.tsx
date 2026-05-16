import { Sparkles } from 'lucide-react'

const TR_FORMATTER = new Intl.NumberFormat('tr-TR')

interface XPBadgeProps {
  total: number
}

export function XPBadge({ total }: XPBadgeProps) {
  return (
    <span
      aria-label="Toplam XP"
      className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 shadow-sm transition-colors hover:border-accent/50"
    >
      <Sparkles aria-hidden="true" className="h-3.5 w-3.5 text-accent" />
      <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
        XP
      </span>
      <span className="font-display text-base font-semibold tabular-nums text-foreground">
        {TR_FORMATTER.format(total)}
      </span>
    </span>
  )
}
