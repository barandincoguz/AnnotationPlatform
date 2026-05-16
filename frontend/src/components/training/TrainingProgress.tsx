import { Fragment } from 'react'
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
    <ol className="mb-6 flex items-center justify-between">
      {LABELS.map((label, i) => {
        const done = i < activeIndex
        const active = i === activeIndex
        const isLast = i === LABELS.length - 1
        return (
          <Fragment key={label}>
            <li
              aria-current={active ? 'step' : undefined}
              className="flex flex-col items-center gap-1.5"
            >
              <span
                className={cn(
                  'inline-flex h-7 w-7 items-center justify-center rounded-full text-xs font-mono font-medium border-2 transition-colors',
                  done && 'bg-success text-success-foreground border-success',
                  active && 'bg-primary text-primary-foreground border-primary',
                  !done && !active && 'border-border text-muted-foreground bg-card',
                )}
              >
                {i + 1}
              </span>
              <span className={cn(
                'font-mono text-[10px] uppercase tracking-wider',
                active ? 'text-foreground font-medium' : 'text-muted-foreground',
              )}>
                {label}
              </span>
            </li>
            {!isLast && (
              <li aria-hidden className="h-px flex-1 bg-border mx-1 mb-5" />
            )}
          </Fragment>
        )
      })}
    </ol>
  )
}
