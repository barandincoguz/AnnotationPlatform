import { Button } from '@/components/ui/button'
import { useTrainingStore } from '@/stores/trainingStore'
import { useAuthStore } from '@/stores/authStore'

interface SummaryStepProps {
  onAnnotate: () => void
  onRetry: () => void
  onBackToHelp: () => void
}

export function SummaryStep({ onAnnotate, onRetry, onBackToHelp }: SummaryStepProps) {
  const degraded = useTrainingStore((s) => s.degraded)
  const quizResult = useTrainingStore((s) => s.quizResult)
  const docResults = useTrainingStore((s) => s.docResults)
  const goldDocs = useTrainingStore((s) => s.goldDocs)
  const user = useAuthStore((s) => s.user)
  const passed = !!user?.has_passed_training

  if (degraded) {
    return (
      <section aria-labelledby="summary-degraded-heading" className="space-y-4">
        <h2 id="summary-degraded-heading" className="text-xl font-semibold">Sonuç</h2>
        <p className="text-sm">Bu attempt için detaylar yeniden yüklenemedi.</p>
        <p className="text-sm">Genel durum: <strong>{passed ? 'Geçti' : 'Geçemedi'}</strong></p>
        <div className="flex gap-2">
          {passed
            ? <Button onClick={onAnnotate}>Anotasyona Başla ▸</Button>
            : <Button onClick={onRetry}>Tekrar Dene</Button>}
        </div>
      </section>
    )
  }

  const passedDocs = goldDocs.filter((g) => docResults[g.gold_id]?.passed).length

  if (passed) {
    return (
      <section aria-labelledby="summary-pass-heading" className="space-y-4">
        <h2 id="summary-pass-heading" className="text-xl font-semibold">🎉 Tebrikler! Eğitimi geçtin</h2>
        <div className="space-y-1 rounded-md border bg-card p-4 text-sm">
          {quizResult && (
            <p>Quiz: <strong>{quizResult.score}/{quizResult.total}</strong> {quizResult.score >= 4 ? '✓ Geçti' : '✗ Geçemedi'}</p>
          )}
          {goldDocs.map((g, i) => {
            const r = docResults[g.gold_id]
            return <p key={g.gold_id}>Doc {i + 1}: <strong>{r ? `${r.matched_count}/${r.expected_count}` : '—'}</strong> {r?.passed ? '✓ Geçti' : '✗ Geçemedi'}</p>
          })}
          <p>Anot. geçen: {passedDocs} / 3 (gerekli: 2)</p>
          <p className="mt-2 font-semibold">Overall: GEÇTI</p>
        </div>
        <Button onClick={onAnnotate} size="lg">Anotasyona Başla ▸</Button>
      </section>
    )
  }

  return (
    <section aria-labelledby="summary-fail-heading" className="space-y-4">
      <h2 id="summary-fail-heading" className="text-xl font-semibold">Eğitimi geçemedin</h2>
      <div className="space-y-1 rounded-md border bg-card p-4 text-sm">
        {quizResult && (
          <p>Quiz: <strong>{quizResult.score}/{quizResult.total}</strong> {quizResult.score >= 4 ? '✓ Geçti' : '✗ Geçemedi (eşik 4)'}</p>
        )}
        {goldDocs.map((g, i) => {
          const r = docResults[g.gold_id]
          return <p key={g.gold_id}>Doc {i + 1}: <strong>{r ? `${r.matched_count}/${r.expected_count}` : '—'}</strong> {r?.passed ? '✓ Geçti' : '✗ Geçemedi'}</p>
        })}
        <p>Anot. geçen: {passedDocs} / 3 (gerekli: 2)</p>
        <p className="mt-2 font-semibold">Overall: GEÇEMEDİ</p>
      </div>
      <div className="flex gap-2">
        <Button onClick={onRetry}>Tekrar Dene</Button>
        <Button onClick={onBackToHelp} variant="ghost">← Kılavuza dön</Button>
      </div>
    </section>
  )
}
