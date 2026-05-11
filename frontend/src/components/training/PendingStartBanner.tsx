import { Button } from '@/components/ui/button'

interface PendingStartBannerProps {
  onDismiss: () => void
  onStartNew: () => void
}

export function PendingStartBanner({ onDismiss, onStartNew }: PendingStartBannerProps) {
  return (
    <div role="alert" className="mx-auto max-w-2xl space-y-3 rounded-md border border-amber-500 bg-amber-50 p-4 dark:bg-amber-950/20">
      <p className="font-medium">⚠ Önceki başlatma yarıda kaldı</p>
      <p className="text-sm">Bir deneme harcanmış olabilir.</p>
      <div className="flex gap-2">
        <Button onClick={onStartNew} size="sm">Yeni denemeyi başlat</Button>
        <Button onClick={onDismiss} variant="ghost" size="sm">Anladım, kapat</Button>
      </div>
    </div>
  )
}
