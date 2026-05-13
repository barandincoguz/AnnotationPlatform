import { useSkipTrainingMutation } from '@/api/queries/training'
import { TypedConfirmDialog } from '@/components/admin/TypedConfirmDialog'

interface SkipConfirmDialogProps {
  open: boolean
  onClose: () => void
}

export function SkipConfirmDialog({ open, onClose }: SkipConfirmDialogProps) {
  const skip = useSkipTrainingMutation()

  return (
    <TypedConfirmDialog
      open={open}
      title="⚠ Eğitimi atlamak asla önerilmez"
      body={
        <>
          <p>Eğitimi atlamak şu riskleri taşır:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>Annotation kaliten düşer; düzeltme zamanı maliyetli.</li>
            <li>Diğer bursiyerlerin review yükü artar.</li>
            <li>Bu karar <strong>kalıcıdır</strong> — geri dönüş yok.</li>
          </ul>
        </>
      }
      confirmWord="SKIP"
      confirmLabel="Eğitimi Atla"
      pendingLabel="Atlanıyor..."
      isPending={skip.isPending}
      onConfirm={() => skip.mutate()}
      onClose={onClose}
    />
  )
}
