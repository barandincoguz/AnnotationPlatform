export function Annotate() {
  return (
    <div
      className="flex h-full flex-col items-center justify-center gap-5 px-8 text-center"
      data-testid="stub-annotate"
    >
      <span
        aria-hidden
        className="font-display text-7xl font-medium text-muted-foreground/15 leading-none"
      >
        №
      </span>
      <div className="space-y-2 max-w-sm">
        <p className="font-display text-2xl font-medium tracking-tight text-foreground">
          Bir özelge seçin.
        </p>
        <p className="text-sm text-muted-foreground leading-relaxed">
          Sol panelden bir doküman seçince burada kanun atıfı çıkarımı paneli
          açılır.
        </p>
      </div>
      <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground/60">
        Yeni · Devam Eden · Tamamlanan
      </p>
    </div>
  )
}
