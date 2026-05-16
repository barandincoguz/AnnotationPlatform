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
    <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-2.5 py-0.5 shadow-sm">
      {done && (
        <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-success">
          Bugün ✓
        </span>
      )}
      <div
        role="progressbar"
        aria-valuenow={today}
        aria-valuemax={target}
        aria-valuemin={0}
        className="h-1 w-16 rounded-full bg-muted overflow-hidden"
      >
        <div
          data-testid="daily-progress-fill"
          className={`h-full rounded-full ${done ? 'bg-success' : 'bg-primary'}`}
          style={{ width: pct }}
        />
      </div>
      <span className={`font-mono text-[10px] tabular-nums ${done ? 'text-success' : 'text-muted-foreground'}`}>
        {today}/{target}
      </span>
    </div>
  )
}
