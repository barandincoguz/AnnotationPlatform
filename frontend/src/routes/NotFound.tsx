import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'

export function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-background px-8 text-center">
      <p
        aria-hidden
        className="font-display text-[10rem] leading-none font-medium text-muted-foreground/15"
      >
        404
      </p>
      <div className="space-y-2 max-w-md -mt-4">
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
          Sayfa bulunamadı
        </p>
        <p className="font-display text-3xl font-medium tracking-tight">
          Aradığın sayfa burada değil.
        </p>
        <p className="text-sm text-muted-foreground leading-relaxed">
          URL hatalı olabilir veya sayfa kaldırılmış olabilir.
        </p>
      </div>
      <Button
        asChild
        className="h-11 bg-primary text-primary-foreground hover:bg-primary/90 font-medium tracking-wide"
      >
        <Link to="/">
          Ana sayfaya dön
          <span aria-hidden className="ml-2 text-primary-foreground/60">→</span>
        </Link>
      </Button>
    </div>
  )
}
