import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { useRetentionPreview, useRetentionRunNow } from '@/api/queries/admin'

export function RetentionPage() {
  const preview = useRetentionPreview()
  const run = useRetentionRunNow()
  const [confirming, setConfirming] = useState(false)

  const onRun = () => {
    run.mutate(undefined, {
      onSuccess: (r) => {
        toast.success(`${r.total} satır silindi`)
        setConfirming(false)
      },
      onError: (e: Error) => toast.error(`Retention başarısız: ${e.message}`),
    })
  }

  return (
    <div className="space-y-4">
      <div className="mb-6 space-y-1">
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
          Operations · Retention
        </p>
        <h1 className="font-display text-3xl font-medium tracking-tight">Retention</h1>
        <p className="text-sm text-muted-foreground max-w-prose">
          Süresi dolan denetim ve sistem olaylarını politika tablolarına göre temizler.
        </p>
      </div>

      {preview.isLoading && <div className="text-sm">Yükleniyor…</div>}
      {preview.isError && (
        <div className="rounded border border-destructive p-4 text-sm">
          Retention önizlemesi alınamadı.
        </div>
      )}
      {preview.data && (
        <div className="rounded-lg border border-border/70 bg-card/40 p-4 space-y-2">
          <div className="text-sm">
            Toplam silinecek satır:{' '}
            <strong data-testid="retention-total">{preview.data.total}</strong>
          </div>
          {Object.keys(preview.data.rows_to_purge).length > 0 && (
            <ul className="text-sm">
              {Object.entries(preview.data.rows_to_purge).map(([t, n]) => (
                <li key={t}>
                  <code>{t}</code>: {n}
                </li>
              ))}
            </ul>
          )}
          {preview.data.policy.length > 0 && (
            <div className="text-xs text-muted-foreground">
              Politika:{' '}
              {preview.data.policy
                .map((p) => `${p.table}=${p.days}d`)
                .join(', ')}
            </div>
          )}
        </div>
      )}

      <Button
        onClick={() => setConfirming(true)}
        disabled={!preview.data || preview.data.total === 0}
      >
        Şimdi temizle
      </Button>

      {confirming && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-40 bg-black/60 grid place-items-center"
        >
          <div className="bg-card border border-border rounded-lg p-6 max-w-md space-y-3">
            <h2 className="text-lg font-medium">Onay</h2>
            <p className="text-sm">
              <strong>{preview.data?.total}</strong> satır kalıcı olarak silinecek. Geri
              alınamaz.
            </p>
            <div className="flex gap-2 justify-end">
              <Button
                variant="ghost"
                onClick={() => setConfirming(false)}
                disabled={run.isPending}
              >
                Vazgeç
              </Button>
              <Button onClick={onRun} disabled={run.isPending}>
                {run.isPending ? 'Siliniyor…' : 'Evet, sil'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
