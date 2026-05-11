import { AlertCircle, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface LoadingScreenProps {
  mode?: 'loading' | 'error'
  onRetry?: () => void
}

export function LoadingScreen({ mode = 'loading', onRetry }: LoadingScreenProps) {
  if (mode === 'error') {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
        <AlertCircle className="h-10 w-10 text-destructive" aria-hidden />
        <p className="text-lg font-medium">Sunucuya bağlanılamadı</p>
        <p className="text-sm text-muted-foreground">
          Bağlantınızı kontrol edin veya tekrar deneyin.
        </p>
        {onRetry && (
          <Button onClick={onRetry} variant="default">
            Tekrar dene
          </Button>
        )}
      </div>
    )
  }
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" aria-hidden />
      <p className="text-sm text-muted-foreground">Yükleniyor…</p>
    </div>
  )
}
