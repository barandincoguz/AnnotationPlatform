import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from '@/components/ui/tooltip'

interface StreakCounterProps {
  current: number
  longest: number
}

function tierClass(current: number): string {
  if (current >= 7) return 'text-red-600'
  if (current >= 4) return 'text-orange-500'
  return 'text-muted-foreground'
}

export function StreakCounter({ current, longest }: StreakCounterProps) {
  const display = current === 0 ? '—' : String(current)
  const showLongest = longest > current

  const inner = (
    <span
      aria-label={`${current} gün streak`}
      className={`inline-flex items-center gap-1 text-sm font-medium ${tierClass(current)}`}
    >
      <span aria-hidden="true">🔥</span>
      <span>{display}</span>
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
