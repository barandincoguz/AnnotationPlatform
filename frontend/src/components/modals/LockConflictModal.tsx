import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

interface LockConflictModalProps {
  open: boolean
  conflictUsername: string | null
  isSameUser: boolean
  onClose: () => void
}

export function LockConflictModal({
  open,
  conflictUsername,
  isSameUser,
  onClose,
}: LockConflictModalProps) {
  const title = isSameUser
    ? 'Bu doküman başka sekmede açık'
    : `${conflictUsername ?? 'Başka bir kullanıcı'} düzenliyor`

  const desc = isSameUser
    ? 'Bu dokümanı başka bir sekmede zaten açtınız. O sekmeye geçin veya bu sekmeyi kapatın.'
    : 'Bu doküman şu anda başka bir kullanıcı tarafından düzenleniyor. Listeye dönüp başka bir doküman seçebilirsiniz.'

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{desc}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button onClick={onClose}>Listeye dön</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
