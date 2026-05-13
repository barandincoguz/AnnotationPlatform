import { TypedConfirmDialog } from './TypedConfirmDialog'

interface Props {
  open: boolean
  title: string
  oldValue: unknown
  newValue: unknown
  confirmWord: string
  isPending?: boolean
  onConfirm: () => void
  onClose: () => void
}

export function DiffPreviewDialog({
  open, title, oldValue, newValue, confirmWord,
  isPending, onConfirm, onClose,
}: Props) {
  const oldJson = JSON.stringify(oldValue, null, 2)
  const newJson = JSON.stringify(newValue, null, 2)
  return (
    <TypedConfirmDialog
      open={open}
      title={title}
      body={
        <div className="space-y-3">
          <p>Bu değişiklik tüm gelecek bursiyerlerin training pass/fail sonuçlarını etkileyecek.</p>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <div className="font-semibold">Eski</div>
              <pre className="overflow-x-auto rounded bg-red-50 p-2">{oldJson}</pre>
            </div>
            <div>
              <div className="font-semibold">Yeni</div>
              <pre className="overflow-x-auto rounded bg-green-50 p-2">{newJson}</pre>
            </div>
          </div>
        </div>
      }
      confirmWord={confirmWord}
      {...(isPending !== undefined ? { isPending } : {})}
      onConfirm={onConfirm}
      onClose={onClose}
    />
  )
}
