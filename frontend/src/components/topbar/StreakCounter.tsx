import { Flame } from 'lucide-react'
import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from '@/components/ui/tooltip'

interface StreakCounterProps {
  current: number
  longest: number
}

function tierClass(current: number): string {
  if (current >= 7) return 'text-destructive'
  if (current >= 4) return 'text-warning'
  return 'text-muted-foreground'
}

export function StreakCounter({ current, longest }: StreakCounterProps) {
  const display = current === 0 ? '—' : String(current)
  const showLongest = longest > current

  const inner = (
    <span
      aria-label={`${current} gün streak`}
      className={`inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-0.5 shadow-sm ${tierClass(current)}`}
    >
      <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-muted-foreground">Streak</span>
      <Flame aria-hidden="true" className="h-3 w-3 shrink-0" />
      <span className="font-display text-sm font-medium tabular-nums">{display}</span>
    </span>
  )

  if (!showLongest) return inner

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>{inner}</TooltipTrigger>
        <TooltipContent>En uzun: {longest} gün</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
