import { useState } from 'react'
import { toast } from 'sonner'
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
    const n = Number(trimmed)
    if (!trimmed || !Number.isFinite(n) || n <= 0) return
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
      <h1 className="text-2xl font-semibold">Document Lock Force-Release</h1>
      <div className="rounded border border-destructive/40 bg-destructive/5 p-3 text-sm">
        ⚠ Bu işlem geri alınamaz. Lock'u tutan kullanıcının kaydedilmemiş değişiklikleri kaybolabilir.
      </div>
      <div className="space-y-2">
        <label htmlFor="lock-doc-id" className="block text-sm font-medium">Document ID</label>
        <Input id="lock-doc-id" inputMode="numeric" pattern="\d+"
          value={docIdText} onChange={(e) => setDocIdText(e.target.value)} />
      </div>
      <Button variant="destructive" onClick={onOpen}>Kilidi Aç</Button>
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
