import { useState } from 'react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useSkipTrainingMutation } from '@/api/queries/training'

interface SkipConfirmDialogProps {
  open: boolean
  onClose: () => void
}

export function SkipConfirmDialog({ open, onClose }: SkipConfirmDialogProps) {
  const [confirmText, setConfirmText] = useState('')
  const skip = useSkipTrainingMutation()
  const canSubmit = confirmText.trim() === 'SKIP' && !skip.isPending

  const handleOpenChange = (o: boolean) => {
    if (!o) {
      setConfirmText('')
      onClose()
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>⚠ Eğitimi atlamak asla önerilmez</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          <p>Eğitimi atlamak şu riskleri taşır:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>Annotation kaliten düşer; düzeltme zamanı maliyetli.</li>
            <li>Diğer bursiyerlerin review yükü artar.</li>
            <li>Bu karar <strong>kalıcıdır</strong> — geri dönüş yok.</li>
          </ul>
          <p>Devam etmek için aşağıya <strong>SKIP</strong> yazın:</p>
          <Input
            // eslint-disable-next-line jsx-a11y/no-autofocus -- dialog input must capture focus for typed-gate flow
            autoFocus
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            placeholder="SKIP"
            aria-label="SKIP yazınız"
          />
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={onClose}
            disabled={skip.isPending}
          >
            Vazgeç
          </Button>
          <Button
            variant="destructive"
            disabled={!canSubmit}
            onClick={() => skip.mutate()}
          >
            {skip.isPending ? 'Atlanıyor...' : 'Eğitimi Atla'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
