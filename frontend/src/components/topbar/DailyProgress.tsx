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
    <div className="flex items-center gap-2 text-sm">
      <div
        role="progressbar"
        aria-valuenow={today}
        aria-valuemax={target}
        aria-valuemin={0}
        className="h-2 w-20 rounded-full bg-muted overflow-hidden"
      >
        <div
          data-testid="daily-progress-fill"
          className={`h-full ${done ? 'bg-green-500' : 'bg-primary'}`}
          style={{ width: pct }}
        />
      </div>
      <span className={done ? 'text-green-600 font-medium' : 'text-muted-foreground'}>
        {today}/{target}{done ? ' Bugün ✓' : ''}
      </span>
    </div>
  )
}
