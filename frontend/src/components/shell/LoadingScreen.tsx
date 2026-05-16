import { AlertCircle, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface LoadingScreenProps {
  mode?: 'loading' | 'error'
  onRetry?: () => void
}

export function LoadingScreen({ mode = 'loading', onRetry }: LoadingScreenProps) {
  if (mode === 'error') {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-background px-8 text-center">
        <div
          aria-hidden
          className="grid h-14 w-14 place-items-center rounded-full border border-destructive/30 bg-destructive/5"
        >
          <AlertCircle className="h-7 w-7 text-destructive" />
        </div>
        <div className="space-y-2 max-w-sm">
          <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
            Bağlantı hatası
          </p>
          <p className="font-display text-2xl font-medium tracking-tight">
            Sunucuya bağlanılamadı.
          </p>
          <p className="text-sm text-muted-foreground leading-relaxed">
            Bağlantınızı kontrol edin veya birkaç saniye sonra tekrar deneyin.
          </p>
        </div>
        {onRetry && (
          <Button
            onClick={onRetry}
            className="h-11 bg-primary text-primary-foreground hover:bg-primary/90 font-medium tracking-wide"
          >
            Tekrar dene
            <span aria-hidden className="ml-2 text-primary-foreground/60">↻</span>
          </Button>
        )}
      </div>
    )
  }
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-5 bg-background">
      <div className="relative">
        <Loader2 className="h-10 w-10 animate-spin text-accent" aria-hidden />
        <span
          aria-hidden
          className="absolute inset-0 grid place-items-center font-display text-[11px] font-semibold text-foreground"
        >
          A
        </span>
      </div>
      <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
        Yükleniyor…
      </p>
    </div>
  )
}
