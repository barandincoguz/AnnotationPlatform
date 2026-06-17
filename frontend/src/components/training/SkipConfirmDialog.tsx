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
      title="Eğitimi atlamak önerilmez"
      description="Eğitimi atlamak kalite ve inceleme yükü açısından risklidir; devam etmek için onay kelimesi istenir."
      body={
        <>
          <p>Eğitimi atlamak şu riskleri taşır:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>Etiketleme kaliten düşebilir ve sonradan düzeltme maliyeti artar.</li>
            <li>Diğer kullanıcıların inceleme yükü artar.</li>
            <li>Bu karar <strong>kalıcıdır</strong>; geri dönüş yok.</li>
          </ul>
        </>
      }
      confirmWord="ATLA"
      confirmLabel="Eğitimi atla"
      pendingLabel="Atlanıyor..."
      isPending={skip.isPending}
      onConfirm={() => skip.mutate()}
      onClose={onClose}
    />
  )
}
