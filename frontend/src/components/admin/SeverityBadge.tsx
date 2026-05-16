interface SeverityBadgeProps {
  severity: string
}

function badgeClass(severity: string): string {
  switch (severity) {
    case 'error':
      return 'bg-destructive/15 text-destructive border-destructive/30'
    case 'warn':
      return 'bg-warning/15 text-warning border-warning/30'
    default:
      return 'bg-muted text-muted-foreground border-border'
  }
}

export function SeverityBadge({ severity }: SeverityBadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.18em] ${badgeClass(severity)}`}
    >
      {severity}
    </span>
  )
}
