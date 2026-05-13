import { useState, useEffect, type ReactNode } from 'react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

interface Props {
  open: boolean
  title: string
  body: ReactNode
  confirmWord: string
  confirmLabel?: string
  pendingLabel?: string
  variant?: 'destructive' | 'default'
  isPending?: boolean
  onConfirm: () => void
  onClose: () => void
}

export function TypedConfirmDialog({
  open, title, body, confirmWord,
  confirmLabel = 'Onayla', pendingLabel = 'Çalışıyor...',
  variant = 'destructive', isPending = false,
  onConfirm, onClose,
}: Props) {
  const [text, setText] = useState('')

  useEffect(() => {
    if (!open) setText('')
  }, [open])

  const canSubmit = text.trim() === confirmWord && !isPending

  const handleOpenChange = (o: boolean) => {
    if (!o) {
      setText('')
      onClose()
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          {body}
          <p>Devam etmek için aşağıya <strong>{confirmWord}</strong> yazın:</p>
          <Input
            // eslint-disable-next-line jsx-a11y/no-autofocus -- dialog input must capture focus for typed-gate flow
            autoFocus
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={confirmWord}
            aria-label={`${confirmWord} yazınız`}
          />
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => { setText(''); onClose() }}
            disabled={isPending}
          >
            Vazgeç
          </Button>
          <Button
            variant={variant}
            disabled={!canSubmit}
            onClick={onConfirm}
          >
            {isPending ? pendingLabel : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
