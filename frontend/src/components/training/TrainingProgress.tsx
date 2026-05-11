import { cn } from '@/lib/utils'
import type { TrainingStep } from '@/stores/trainingStore'

interface TrainingProgressProps {
  step: TrainingStep
  docIndex: 0 | 1 | 2
}

const LABELS = ['Quiz', 'Doc 1', 'Doc 2', 'Doc 3', 'Sonuç']

export function TrainingProgress({ step, docIndex }: TrainingProgressProps) {
  const activeIndex =
    step === 'quiz' ? 0
    : step === 'doc' ? 1 + docIndex
    : step === 'summary' ? 4
    : -1

  return (
    <ol className="mb-6 flex items-center justify-between gap-2">
      {LABELS.map((label, i) => {
        const done = i < activeIndex
        const active = i === activeIndex
        return (
          <li
            key={label}
            aria-current={active ? 'step' : undefined}
            className="flex flex-1 flex-col items-center gap-1"
          >
            <span
              className={cn(
                'flex h-6 w-6 items-center justify-center rounded-full border text-xs',
                done && 'border-primary bg-primary text-primary-foreground',
                active && 'border-primary bg-background font-semibold text-primary',
                !done && !active && 'border-muted-foreground text-muted-foreground',
              )}
            >
              {done ? '●' : active ? '◉' : '○'}
            </span>
            <span className={cn('text-xs', active && 'font-medium')}>{label}</span>
          </li>
        )
      })}
    </ol>
  )
}
