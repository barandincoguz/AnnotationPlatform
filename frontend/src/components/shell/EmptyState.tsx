import { cn } from '@/lib/utils'

interface EmptyStateProps {
  /** Mono kicker, e.g. "Boş" / "Bulunamadı". Optional. */
  kicker?: string
  /** Big display headline / message. */
  title: string
  /** Optional smaller body sentence. */
  description?: string
  /** Optional ornament glyph rendered huge in muted/15. Defaults to "№". */
  ornament?: string
  /** Optional action node (button etc.) below the description. */
  action?: React.ReactNode
  className?: string
}

/**
 * Editorial empty state — huge translucent ornament glyph + mono kicker
 * + Fraunces display title + optional description + optional action.
 * Single source of truth so empty states across DocList, AdminTable,
 * BadgesGrid, NotificationsList read with the same visual rhythm.
 */
export function EmptyState({
  kicker = 'Boş',
  title,
  description,
  ornament = '№',
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-3 py-12 text-center',
        className,
      )}
    >
      <span
        aria-hidden
        className="font-display text-5xl font-medium text-muted-foreground/20 leading-none"
      >
        {ornament}
      </span>
      <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
        {kicker}
      </p>
      <p className="font-display text-xl font-medium tracking-tight text-foreground max-w-sm">
        {title}
      </p>
      {description && (
        <p className="text-sm text-muted-foreground max-w-sm leading-relaxed">
          {description}
        </p>
      )}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}
