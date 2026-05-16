import { AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface PendingStartBannerProps {
  onDismiss: () => void
  onStartNew: () => void
}

export function PendingStartBanner({ onDismiss, onStartNew }: PendingStartBannerProps) {
  return (
    <div role="alert" className="mx-auto max-w-2xl space-y-3 rounded-md border border-warning/40 bg-warning/5 p-4">
      <p className="flex items-center gap-1.5 font-medium">
        <AlertTriangle className="h-4 w-4 text-warning" aria-hidden />
        Önceki başlatma yarıda kaldı
      </p>
      <p className="text-sm">Bir deneme harcanmış olabilir.</p>
      <div className="flex gap-2">
        <Button onClick={onStartNew} size="sm">Yeni denemeyi başlat</Button>
        <Button onClick={onDismiss} variant="ghost" size="sm">Anladım, kapat</Button>
      </div>
    </div>
  )
}
