import { useDoc } from '@/hooks/useDoc'

interface DocViewerProps {
  docId: string
}

export function DocViewer({ docId }: DocViewerProps) {
  const q = useDoc(docId)
  if (q.isPending) {
    return <div className="p-4 text-sm text-muted-foreground">Yükleniyor…</div>
  }
  if (q.error || !q.data) {
    return <div className="p-4 text-sm text-destructive">Doküman yüklenemedi.</div>
  }
  const d = q.data
  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="border-b border-border p-3 text-sm">
        <div className="font-semibold">
          #{d.sayi ?? '—'} · {d.tarih ?? '—'}
        </div>
        <div className="flex items-center gap-2 mt-1 text-muted-foreground text-xs">
          {d.vergi_turu && <span className="rounded bg-muted px-2 py-0.5">{d.vergi_turu}</span>}
          {d.konu && <span className="line-clamp-1">{d.konu}</span>}
        </div>
      </header>
      <article className="flex-1 overflow-auto whitespace-pre-wrap p-4 text-sm leading-relaxed">
        {d.pdf_text}
      </article>
    </div>
  )
}
