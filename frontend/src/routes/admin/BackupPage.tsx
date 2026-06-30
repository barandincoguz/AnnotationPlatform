import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { useBackupHistory, useBackupRunNow } from '@/api/queries/admin'

function backupEventLabel(eventType: string) {
  if (eventType === 'backup_skipped_no_remote') {
    return 'backup_skipped_no_remote · GitHub’a gönderilmedi'
  }
  return eventType
}

export function BackupPage() {
  const history = useBackupHistory()
  const run = useBackupRunNow()

  const onRun = () => {
    run.mutate(undefined, {
      onSuccess: (result) => {
        if (result.pushed) {
          toast.success('Yedek alındı ve GitHub’a gönderildi')
          return
        }
        toast.warning('Yedek alındı, ancak GitHub’a gönderilmedi')
      },
      onError: (e: Error) => toast.error(`Yedek başarısız: ${e.message}`),
    })
  }

  return (
    <div className="space-y-4">
      <div className="mb-6 space-y-1">
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
          Operations · Backup
        </p>
        <h1 className="font-display text-3xl font-medium tracking-tight">Backup</h1>
        <p className="text-sm text-muted-foreground max-w-prose">
          Veritabanı snapshot&apos;larını manuel olarak tetikle ve son 20 yedek olayını gör.
        </p>
      </div>

      <div className="flex items-center gap-3">
        <Button onClick={onRun} disabled={run.isPending}>
          {run.isPending ? 'Yedek alınıyor…' : 'Şimdi yedek al'}
        </Button>
        {run.data?.committed_sha ? (
          <span className="font-mono text-xs text-muted-foreground">
            sha: {run.data.committed_sha.slice(0, 7)} · pushed:{' '}
            {run.data.pushed ? 'evet' : 'hayır'}
          </span>
        ) : null}
      </div>

      <div className="rounded-lg border border-border/70 bg-card/40 p-4">
        <h2 className="font-medium mb-3">Son 20 yedek olayı</h2>
        {history.isLoading && <div className="text-sm">Yükleniyor…</div>}
        {history.isError && (
          <div className="text-sm text-destructive">Yedek geçmişi alınamadı.</div>
        )}
        {history.data?.items.length === 0 && (
          <div className="text-sm text-muted-foreground">Henüz yedek alınmamış.</div>
        )}
        {(history.data?.items.length ?? 0) > 0 && (
          <ul className="space-y-2 text-sm">
            {history.data?.items.map((e) => (
              <li key={e.id} className="flex items-baseline gap-3">
                <span className="font-mono text-xs text-muted-foreground w-44 shrink-0">
                  {e.created_at}
                </span>
                <span
                  className={`text-xs px-1.5 rounded ${
                    e.severity === 'error'
                      ? 'bg-destructive/15 text-destructive'
                      : e.severity === 'warn'
                        ? 'bg-amber-100 text-amber-800'
                        : 'bg-muted text-muted-foreground'
                  }`}
                >
                  {backupEventLabel(e.event_type)}
                </span>
                <span>{e.message}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
