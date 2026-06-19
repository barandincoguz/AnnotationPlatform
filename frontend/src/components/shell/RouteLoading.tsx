import { Loader2 } from 'lucide-react'

export function RouteLoading() {
  return (
    <div
      role="status"
      aria-live="polite"
      className="grid min-h-[12rem] w-full place-items-center bg-background"
    >
      <div className="flex items-center gap-3 text-sm text-muted-foreground">
        <Loader2 aria-hidden className="h-5 w-5 animate-spin text-accent" />
        <span>Sayfa yükleniyor…</span>
      </div>
    </div>
  )
}
