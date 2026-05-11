import { useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
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
    return (
      <section aria-labelledby="quiz-result-heading">
        <h2 ref={headingRef} tabIndex={-1} id="quiz-result-heading" className="text-xl font-semibold focus:outline-none">
          Quiz tamamlandı
        </h2>
        <div role="status" aria-live="polite" className="mt-4 rounded-md border bg-card p-4 text-sm">
          ✓ Skor: <strong>{quizResult.score} / {quizResult.total}</strong>
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
          <fieldset key={q.id} className="rounded-md border p-4">
            <legend className="px-2 text-sm font-medium">{idx + 1}. {q.text}</legend>
            <div className="mt-2 space-y-2">
              {q.choices.map((choice, ci) => (
                <label key={ci} className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name={q.id}
                    value={ci}
                    checked={quizAnswers[q.id] === ci}
                    onChange={() => setQuizAnswer(q.id, ci)}
                    disabled={isSubmitting}
                    className="h-4 w-4"
                  />
                  {choice}
                </label>
              ))}
            </div>
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
