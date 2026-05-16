import { useState } from 'react'
import { toast } from 'sonner'
import { AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { TypedConfirmDialog } from '@/components/admin/TypedConfirmDialog'
import { useForceReleaseLockMutation } from '@/api/queries/admin'

export function LocksPage() {
  const [docIdText, setDocIdText] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const release = useForceReleaseLockMutation()

  const onOpen = () => {
    const trimmed = docIdText.trim()
    if (!trimmed) return
    setDialogOpen(true)
  }

  const onConfirm = () => {
    release.mutate(docIdText.trim(), {
      onSuccess: () => {
        toast.success('Lock açıldı')
        setDocIdText('')
        setDialogOpen(false)
      },
      onError: (err: unknown) => {
        const status = (err as { status?: number })?.status
        if (status === 404) {
          toast.warning('Bu dokümanın aktif lock yok')
        } else {
          toast.error('Lock açılamadı')
        }
        setDialogOpen(false)
      },
    })
  }

  return (
    <div className="max-w-md space-y-4">
      <div className="mb-6 space-y-1">
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
          Operations · Locks
        </p>
        <h1 className="font-display text-3xl font-medium tracking-tight">
          Force-release Lock
        </h1>
        <p className="text-sm text-muted-foreground max-w-prose">
          Forcibly remove an active document lock held by any user.
        </p>
      </div>
      <div className="rounded border border-destructive/40 bg-destructive/5 p-3 text-sm">
        ⚠ Bu işlem geri alınamaz. Lock&apos;u tutan kullanıcının kaydedilmemiş değişiklikleri kaybolabilir.
      </div>
      <div className="space-y-2">
        <label htmlFor="lock-doc-id" className="block text-sm font-medium">Document ID</label>
        <Input id="lock-doc-id"
          value={docIdText} onChange={(e) => setDocIdText(e.target.value)} />
      </div>
      <Button variant="destructive" onClick={onOpen}>Kilidi Aç</Button>
      {release.isError && (
        <div className="flex items-center gap-3 rounded-md border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden />
          {(release.error as { status?: number })?.status === 404
            ? 'Kayıt bulunamadı — lock mevcut değil.'
            : 'İşlem başarısız oldu, lütfen tekrar deneyin.'}
        </div>
      )}
      <TypedConfirmDialog
        open={dialogOpen}
        title="Lock'u zorla aç"
        body={<p>Document #{docIdText} kilidini açmak üzeresin. Bu geri alınamaz.</p>}
        confirmWord="RELEASE"
        isPending={release.isPending}
        onConfirm={onConfirm}
        onClose={() => setDialogOpen(false)}
      />
    </div>
  )
}
