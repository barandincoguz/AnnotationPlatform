interface DailyProgressProps {
  today: number
  target: number
}

export function DailyProgress({ today, target }: DailyProgressProps) {
  if (target === 0) return null
  const ratio = Math.min(today / target, 1)
  const pct = `${Math.round(ratio * 100)}%`
  const done = today >= target

  return (
    <div className="inline-flex items-center gap-2.5 rounded-full border border-border bg-card px-3 py-1 shadow-sm transition-colors hover:border-accent2/50">
      {done && (
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-success">
          Bugün ✓
        </span>
      )}
      <div
        role="progressbar"
        aria-label={`Günlük ilerleme: ${today} / ${target} özelge`}
        aria-valuenow={today}
        aria-valuemax={target}
        aria-valuemin={0}
        className="h-1.5 w-20 rounded-full bg-muted overflow-hidden"
      >
        <div
          data-testid="daily-progress-fill"
          className={`h-full rounded-full transition-[width] duration-500 ${done ? 'bg-success' : 'bg-accent2'}`}
          style={{ width: pct }}
        />
      </div>
      <span
        className={`font-mono text-[11px] font-medium tabular-nums ${done ? 'text-success' : 'text-foreground/75'}`}
      >
        {today}/{target}
      </span>
    </div>
  )
}
