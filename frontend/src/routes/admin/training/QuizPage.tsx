import { useState } from 'react'
import { Loader2, AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAdminQuiz } from '@/api/queries/admin'
import { QuizEditor } from '@/components/admin/training/QuizEditor'

export function QuizPage() {
  const q = useAdminQuiz()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const selected = q.data?.resolved.find((qq) => qq.id === selectedId) ?? null

  if (q.isLoading) return (
    <div className="flex items-center gap-3 rounded-md border border-border/60 bg-card/40 px-4 py-6 text-sm text-muted-foreground">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      Yükleniyor…
    </div>
  )
  if (q.isError || !q.data) return (
    <div className="flex items-center gap-3 rounded-md border border-destructive/40 bg-destructive/5 px-4 py-6 text-sm text-destructive">
      <AlertCircle className="h-4 w-4 shrink-0" aria-hidden />
      Quiz listesi alınamadı
    </div>
  )

  return (
    <div className="space-y-6">
      <div className="mb-6 space-y-1">
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
          Training Content · Quiz
        </p>
        <h1 className="font-display text-3xl font-medium tracking-tight">
          Quiz
        </h1>
        <p className="text-sm text-muted-foreground max-w-prose">
          Manage quiz questions used to assess annotator readiness during training.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-[280px_1fr]">
        <aside className="space-y-2">
          <ul className="space-y-1">
            {q.data.resolved.map((qq) => (
              <li key={qq.id}>
                <button onClick={() => setSelectedId(qq.id)}
                  className={cn(
                    'relative block w-full text-left px-3 py-2 text-sm rounded-md transition-colors',
                    selectedId === qq.id
                      ? 'bg-secondary/70 text-foreground'
                      : 'text-muted-foreground hover:bg-muted/60'
                  )}>
                  {selectedId === qq.id && (
                    <span aria-hidden className="absolute inset-y-1.5 left-0 w-[2px] bg-accent rounded-r" />
                  )}
                  {qq.id}
                </button>
              </li>
            ))}
          </ul>
        </aside>
        <main>
          {selected ? <QuizEditor q={selected} /> : <p className="text-muted-foreground">Soldan bir soru seç</p>}
        </main>
      </div>
    </div>
  )
}
