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
        <h2 id="summary-degraded-heading" className="font-display text-3xl tracking-tight">Sonuç</h2>
        <p className="text-sm text-muted-foreground">Bu attempt için detaylar yeniden yüklenemedi.</p>
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
      <section aria-labelledby="summary-pass-heading" className="space-y-6">
        {/* Pass hero */}
        <div className="rounded-lg border border-success/30 bg-success/10 px-6 py-5">
          <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-success/70 mb-2">
            Eğitim Tamamlandı · {String(passedDocs).padStart(2, '0')} / {String(goldDocs.length).padStart(2, '0')}
          </p>
          <h2 id="summary-pass-heading" className="font-display text-3xl tracking-tight text-success">
            Tebrikler!
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">Eğitimi başarıyla tamamladın.</p>
        </div>

        {/* Score breakdown */}
        <div className="rounded-md border bg-card divide-y divide-border text-sm">
          {quizResult && (
            <div className="flex items-center justify-between px-4 py-3">
              <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Quiz</span>
              <span>
                <strong className="font-display text-base">
                  № {quizResult.score}/{quizResult.total}
                </strong>
                {' '}
                <span className={quizResult.score >= 4 ? 'text-success' : 'text-destructive'}>
                  {quizResult.score >= 4 ? '✓ Geçti' : '✗ Geçemedi'}
                </span>
              </span>
            </div>
          )}
          {goldDocs.map((g, i) => {
            const r = docResults[g.gold_id]
            return (
              <div key={g.gold_id} className="flex items-center justify-between px-4 py-3">
                <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                  Döküman {i + 1}
                </span>
                <span>
                  <strong className="font-display text-base">
                    № {r ? `${r.matched_count}/${r.expected_count}` : '—'}
                  </strong>
                  {' '}
                  <span className={r?.passed ? 'text-success' : 'text-destructive'}>
                    {r?.passed ? '✓ Geçti' : '✗ Geçemedi'}
                  </span>
                </span>
              </div>
            )
          })}
          <div className="flex items-center justify-between px-4 py-3">
            <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Anot. geçen</span>
            <span className="text-sm">{passedDocs} / 3 (gerekli: 2)</span>
          </div>
          <div className="flex items-center justify-between px-4 py-3 bg-success/5">
            <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Overall</span>
            <span className="font-semibold text-success">GEÇTI</span>
          </div>
        </div>

        <Button onClick={onAnnotate} size="lg">Anotasyona Başla ▸</Button>
      </section>
    )
  }

  return (
    <section aria-labelledby="summary-fail-heading" className="space-y-6">
      {/* Fail hero */}
      <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-6 py-5">
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-destructive/70 mb-2">
          Eğitim · Tamamlanamadı
        </p>
        <h2 id="summary-fail-heading" className="font-display text-3xl tracking-tight text-destructive">
          Eğitimi geçemedin
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Eşik değerlerini karşılamak için tekrar deneyebilirsin.
        </p>
      </div>

      {/* Score breakdown */}
      <div className="rounded-md border bg-card divide-y divide-border text-sm">
        {quizResult && (
          <div className="flex items-center justify-between px-4 py-3">
            <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Quiz</span>
            <span>
              <strong className="font-display text-base">
                № {quizResult.score}/{quizResult.total}
              </strong>
              {' '}
              <span className={quizResult.score >= 4 ? 'text-success' : 'text-destructive'}>
                {quizResult.score >= 4 ? '✓ Geçti' : '✗ Geçemedi (eşik 4)'}
              </span>
            </span>
          </div>
        )}
        {goldDocs.map((g, i) => {
          const r = docResults[g.gold_id]
          return (
            <div key={g.gold_id} className="flex items-center justify-between px-4 py-3">
              <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                Döküman {i + 1}
              </span>
              <span>
                <strong className="font-display text-base">
                  № {r ? `${r.matched_count}/${r.expected_count}` : '—'}
                </strong>
                {' '}
                <span className={r?.passed ? 'text-success' : 'text-destructive'}>
                  {r?.passed ? '✓ Geçti' : '✗ Geçemedi'}
                </span>
              </span>
            </div>
          )
        })}
        <div className="flex items-center justify-between px-4 py-3">
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Anot. geçen</span>
          <span className="text-sm">{passedDocs} / 3 (gerekli: 2)</span>
        </div>
        <div className="flex items-center justify-between px-4 py-3 bg-destructive/5">
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Overall</span>
          <span className="font-semibold text-destructive">GEÇEMEDİ</span>
        </div>
      </div>

      <div className="flex gap-2">
        <Button onClick={onRetry}>Tekrar Dene</Button>
        <Button onClick={onBackToHelp} variant="ghost">← Kılavuza dön</Button>
      </div>
    </section>
  )
}
