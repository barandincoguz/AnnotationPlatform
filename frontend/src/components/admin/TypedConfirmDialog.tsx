import { useState, useEffect, type ReactNode } from 'react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

interface Props {
  open: boolean
  title: string
  description?: string
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
  open, title, description, body, confirmWord,
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

  // Wrap the body+footer in a <form> so pressing Enter after typing
  // the confirm word fires the action (the prior dialog only accepted
  // a mouse click). canSubmit is re-checked on submit because Pydantic
  // and Radix can both lag a tick behind the keystroke that triggered
  // the submission.
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (canSubmit) onConfirm()
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription className="sr-only">
            {description ?? 'Bu işlem için yazılı onay gerekiyor.'}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit}>
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
          <DialogFooter className="mt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => { setText(''); onClose() }}
              disabled={isPending}
            >
              Vazgeç
            </Button>
            <Button
              type="submit"
              variant={variant}
              disabled={!canSubmit}
            >
              {isPending ? pendingLabel : confirmLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
