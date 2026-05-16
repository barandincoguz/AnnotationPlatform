import { useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { useTrainingStore } from '@/stores/trainingStore'

interface QuizStepProps {
  onSubmit: (answers: Record<string, number>) => void
  isSubmitting: boolean
}

export function QuizStep({ onSubmit, isSubmitting }: QuizStepProps) {
  const questions = useTrainingStore((s) => s.questions)
  const quizAnswers = useTrainingStore((s) => s.quizAnswers)
  const setQuizAnswer = useTrainingStore((s) => s.setQuizAnswer)
  const resultShown = useTrainingStore((s) => s.resultShown)
  const quizResult = useTrainingStore((s) => s.quizResult)
  const setStep = useTrainingStore((s) => s.setStep)

  const headingRef = useRef<HTMLHeadingElement | null>(null)
  useEffect(() => {
    headingRef.current?.focus()
  }, [resultShown])

  const allAnswered = questions.every((q) => quizAnswers[q.id] !== undefined)

  if (resultShown?.kind === 'quiz' && quizResult) {
    const passed = quizResult.score >= 4
    return (
      <section aria-labelledby="quiz-result-heading">
        <h2 ref={headingRef} tabIndex={-1} id="quiz-result-heading" className="text-xl font-semibold focus:outline-none">
          Quiz tamamlandı
        </h2>
        <div
          role="status"
          aria-live="polite"
          className={cn(
            'mt-4 rounded-md border p-4 text-sm',
            passed
              ? 'bg-success/5 border-success/30'
              : 'bg-destructive/5 border-destructive/30',
          )}
        >
          <span className={passed ? 'text-success font-medium' : 'text-destructive font-medium'}>
            {passed ? '✓' : '✗'}
          </span>{' '}
          Skor: <strong>{quizResult.score} / {quizResult.total}</strong>
          <p className="mt-1 text-xs text-muted-foreground">(Geçmek için ≥4 gerekir)</p>
        </div>
        <div className="mt-6">
          <Button onClick={() => setStep('doc')}>Sonraki: Doküman 1 ▸</Button>
        </div>
      </section>
    )
  }

  return (
    <section aria-labelledby="quiz-heading">
      <h2 ref={headingRef} tabIndex={-1} id="quiz-heading" className="text-xl font-semibold focus:outline-none">
        Quiz
      </h2>
      <p className="mt-2 text-sm text-muted-foreground">
        ⓘ 5 soruyu cevapla, sonra &quot;Cevapları Gönder&quot; tuşuna bas. Skorunu hepsini birden öğreneceksin.
      </p>
      <div className="mt-6 space-y-6">
        {questions.map((q, idx) => (
          <fieldset key={q.id} className="rounded-md border border-border/70 bg-card/40 p-5 space-y-3">
            <legend className="px-2">
              <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
                SORU {String(idx + 1).padStart(2, '0')} / {String(questions.length).padStart(2, '0')}
              </span>
              <span className="ml-2 text-sm font-medium text-foreground">{q.text}</span>
            </legend>
            <RadioGroup
              value={quizAnswers[q.id] !== undefined ? String(quizAnswers[q.id]) : ''}
              onValueChange={(v) => setQuizAnswer(q.id, Number(v))}
              disabled={isSubmitting}
              className="space-y-1 gap-0"
            >
              {q.choices.map((choice, ci) => (
                <label
                  key={ci}
                  htmlFor={`${q.id}-${ci}`}
                  className="flex items-center gap-2 text-sm hover:bg-muted/40 rounded px-2 py-1 cursor-pointer"
                >
                  <RadioGroupItem id={`${q.id}-${ci}`} value={String(ci)} />
                  {choice}
                </label>
              ))}
            </RadioGroup>
          </fieldset>
        ))}
      </div>
      <div className="mt-6">
        <Button onClick={() => onSubmit(quizAnswers)} disabled={!allAnswered || isSubmitting}>
          {isSubmitting ? 'Gönderiliyor...' : 'Cevapları Gönder'}
        </Button>
      </div>
    </section>
  )
}
