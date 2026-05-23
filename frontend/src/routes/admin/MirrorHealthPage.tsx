import { useMirrorHealth } from '@/api/queries/admin'

function queueClass(depth: number): string {
  if (depth >= 10_000) return 'text-destructive font-semibold'
  if (depth >= 1_000) return 'text-amber-600 font-semibold'
  return ''
}

function deadLetterClass(n: number): string {
  if (n > 0) return 'text-amber-600 font-semibold'
  return ''
}

export function MirrorHealthPage() {
  const q = useMirrorHealth()

  return (
    <div className="space-y-4">
      <div className="mb-6 space-y-1">
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
          Operations · Mirror
        </p>
        <h1 className="font-display text-3xl font-medium tracking-tight">
          Neon Mirror Health
        </h1>
        <p className="text-sm text-muted-foreground max-w-prose">
          Async mirror dispatcher state and outbox queue depth. Auto-refresh every 10 s.
        </p>
      </div>

      {q.isLoading && <div className="text-sm">Yükleniyor…</div>}
      {q.isError && (
        <div className="rounded border border-destructive p-4 text-sm">
          Mirror sağlık verisi alınamadı.
        </div>
      )}

      {q.data && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="rounded-lg border border-border/70 bg-card/40 p-4">
            <div className="text-xs text-muted-foreground">Outbox queue depth</div>
            <div data-testid="queue-depth" className={`text-2xl ${queueClass(q.data.queue_depth)}`}>
              {q.data.queue_depth}
            </div>
          </div>
          <div className="rounded-lg border border-border/70 bg-card/40 p-4">
            <div className="text-xs text-muted-foreground">Dead-letter rows</div>
            <div data-testid="dead-letter" className={`text-2xl ${deadLetterClass(q.data.dead_letter_count)}`}>
              {q.data.dead_letter_count}
            </div>
          </div>
          <div className="rounded-lg border border-border/70 bg-card/40 p-4">
            <div className="text-xs text-muted-foreground">Dispatcher</div>
            <div className="text-2xl">
              {q.data.dispatcher_alive ? 'dispatcher alive' : 'dispatcher down'}
            </div>
          </div>
          <div className="rounded-lg border border-border/70 bg-card/40 p-4">
            <div className="text-xs text-muted-foreground">Neon reachable</div>
            <div className="text-2xl">
              {q.data.neon_reachable === null ? '—' : q.data.neon_reachable ? 'evet' : 'hayır'}
            </div>
          </div>
          <div className="rounded-lg border border-border/70 bg-card/40 p-4">
            <div className="text-xs text-muted-foreground">Last delivered at</div>
            <div className="text-base font-mono">
              {q.data.last_delivered_at ?? '—'}
            </div>
          </div>
          <div className="rounded-lg border border-border/70 bg-card/40 p-4">
            <div className="text-xs text-muted-foreground">Oldest undelivered (s)</div>
            <div className="text-base font-mono">
              {q.data.oldest_undelivered_age_seconds == null
                ? '—'
                : q.data.oldest_undelivered_age_seconds.toFixed(1)}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
