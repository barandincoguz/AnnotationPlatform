import { useState, useMemo, useRef, useEffect } from 'react'
import {
  BookMarked,
  BookOpen,
  CalendarDays,
  ClipboardCheck,
  Hash,
  Tag,
  Users,
  AlignLeft,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { useDoc } from '@/hooks/useDoc'
import { formatYmd } from '@/lib/formatters'
import { normalizeOzelgeText } from '@/lib/normalizeOzelgeText'
import { cn } from '@/lib/utils'
import type { components } from '@/api/types'

type DocumentDetail = components['schemas']['DocumentDetail']
type KanunRef = components['schemas']['KanunRef']
type BkkRef = components['schemas']['BkkRef']

interface DocViewerProps {
  docId: string
}

const TR_FORMATTER = new Intl.NumberFormat('tr-TR')

function difficultyTint(difficulty: string): string {
  const lower = difficulty.toLowerCase()
  if (lower === 'kolay') return 'border-success/30 bg-success/10 text-success'
  if (lower === 'orta') return 'border-warning/30 bg-warning/10 text-warning'
  if (lower === 'zor') return 'border-destructive/30 bg-destructive/10 text-destructive'
  return 'border-border bg-muted text-muted-foreground'
}

function MetaField({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof CalendarDays
  label: string
  value: string | number | null | undefined
}) {
  if (value === null || value === undefined || value === '' || value === '—') return null
  return (
    <div className="flex items-center gap-1.5 min-w-0">
      <Icon aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-muted-foreground/80" />
      <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/80 shrink-0">
        {label}:
      </span>
      <span className="font-medium text-[11px] tabular-nums text-foreground truncate">{value}</span>
    </div>
  )
}

function RefList({
  refs,
  icon: Icon,
  title,
  renderItem,
}: {
  refs: readonly (KanunRef | BkkRef)[]
  icon: typeof BookMarked
  title: string
  renderItem: (ref: KanunRef | BkkRef) => React.ReactNode
}) {
  if (refs.length === 0) return null
  return (
    <section className="space-y-1.5">
      <div className="flex items-baseline gap-1.5">
        <Icon aria-hidden="true" className="h-3.5 w-3.5 text-accent" />
        <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">
          {title}
        </span>
        <span className="font-mono text-[10px] font-bold tabular-nums text-foreground/70">
          ({refs.length})
        </span>
      </div>
      <ol className="space-y-1 pl-1">
        {refs.map((ref) => (
          <li
            key={ref.seq}
            className="flex items-baseline gap-2 rounded-md border border-border/40 bg-card/45 px-2.5 py-1 text-[13px]"
          >
            <span className="font-mono text-[10px] font-bold tabular-nums text-accent">
              {String(ref.seq + 1).padStart(2, '0')}.
            </span>
            <span className="flex-1 text-foreground/90 leading-snug">
              {renderItem(ref)}
            </span>
          </li>
        ))}
      </ol>
    </section>
  )
}

function isKanunRef(ref: KanunRef | BkkRef): ref is KanunRef {
  return 'kanun_maddesi' in ref
}

function renderKanunRef(ref: KanunRef | BkkRef) {
  if (!isKanunRef(ref)) return null
  return (
    <>
      <span className="font-semibold">{ref.kanun_kodu}</span>
      {ref.kanun_maddesi && (
        <>
          {' · '}
          <span>Madde {ref.kanun_maddesi}</span>
        </>
      )}
      {ref.kanun_maddesi_turu && (
        <span className="ml-2 inline-flex items-center rounded-full border border-accent/30 bg-accent/10 px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.18em] text-accent">
          {ref.kanun_maddesi_turu}
        </span>
      )}
    </>
  )
}

function renderBkkRef(ref: KanunRef | BkkRef) {
  if (isKanunRef(ref)) return null
  return (
    <>
      {ref.turu && (
        <span className="mr-2 inline-flex items-center rounded-full border border-accent2/30 bg-accent2/10 px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.18em] text-accent2">
          {ref.turu}
        </span>
      )}
      <span className="font-semibold">{ref.kanun_kodu}</span>
      {ref.madde_no && (
        <>
          {' · '}
          <span>Madde {ref.madde_no}</span>
        </>
      )}
    </>
  )
}

function Header({ d }: { d: DocumentDetail }) {
  return (
    <header className="space-y-1.5 border-b border-border/60 bg-card/60 px-5 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="font-display text-[1.125rem] font-bold tracking-tight text-foreground shrink-0">
            ID:
          </span>
          <span
            title="Doküman kimliği (evrakOid)"
            className="font-mono text-[13px] font-bold tracking-tight text-foreground select-all break-all"
          >
            {d.document_id}
          </span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {d.estimated_difficulty && (
            <span
              className={cn(
                'inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.12em]',
                difficultyTint(d.estimated_difficulty),
              )}
            >
              {d.estimated_difficulty}
            </span>
          )}
          {d.word_count > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full border border-border bg-card px-2 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
              <AlignLeft className="h-2.5 w-2.5" />
              {TR_FORMATTER.format(d.word_count)} kelime
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] sm:grid-cols-3 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
        <MetaField icon={CalendarDays} label="Tarih" value={formatYmd(d.tarih)} />
        <MetaField
          icon={ClipboardCheck}
          label="Başvuru"
          value={formatYmd(d.basvuru_tarihi)}
        />
        <MetaField icon={Hash} label="Vergi Türü" value={d.vergi_turu ?? null} />
        <MetaField icon={Tag} label="Dönem" value={d.vergi_donemi ?? null} />
        <MetaField icon={Users} label="Mükellefiyet" value={d.mukellefiyet_turu ?? null} />
        <MetaField icon={Tag} label="Kategori" value={d.topic_category ?? null} />
      </div>

      {d.konu && (
        <div className="border-t border-border/40 pt-1.5 flex gap-1.5 items-baseline text-[12px]">
          <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.15em] text-muted-foreground shrink-0">
            Konu:
          </span>
          <p className="font-medium leading-normal text-foreground/90">
            {d.konu}
          </p>
        </div>
      )}
    </header>
  )
}

export function DocViewer({ docId }: DocViewerProps) {
  const q = useDoc(docId)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const [showRawRefs, setShowRawRefs] = useState(false)

  // Scroll to top on docId change (Bug prevention: prevents sticking to previous scroll)
  useEffect(() => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = 0
    }
  }, [docId])

  // 3-pass regex over multi-KB pdf_text. Memoized so any unrelated
  // parent re-render (zustand tick, child query refetch, typing in
  // the right-pane ReferenceCards if they ever bubble state up) does
  // not re-normalize the entire özelge. Hook MUST run unconditionally
  // (rules-of-hooks) — handle the still-loading case inside the
  // closure with an empty fallback; the early returns below render
  // before `cleaned` is ever read so the empty string is harmless.
  const rawPdfText = q.data?.pdf_text
  const cleaned = useMemo(
    () => (rawPdfText ? normalizeOzelgeText(rawPdfText) : ''),
    [rawPdfText],
  )
  if (q.isPending) {
    return (
      <div role="status" aria-live="polite" className="p-4 text-[15px] text-muted-foreground">
        Yükleniyor…
      </div>
    )
  }
  if (q.error || !q.data) {
    return <div className="p-4 text-[15px] text-destructive">Doküman yüklenemedi.</div>
  }
  const d = q.data
  const hasRefs = d.kanun_refs.length > 0 || d.bkk_refs.length > 0

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <Header d={d} />

      <div ref={scrollContainerRef} className="flex-1 overflow-auto">
        {hasRefs && (
          <div className="border-b border-border/40 bg-secondary/15">
            <button
              type="button"
              onClick={() => setShowRawRefs(!showRawRefs)}
              className="flex w-full items-center justify-between px-5 py-2 text-left hover:bg-secondary/30 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              <div className="flex items-center gap-2">
                <BookMarked className="h-4 w-4 text-accent/80" />
                <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">
                  Kaynak Veri Referansları ({d.kanun_refs.length + d.bkk_refs.length} Atıf)
                </span>
              </div>
              <div className="flex items-center gap-1.5 text-muted-foreground hover:text-foreground">
                <span className="text-[11px] font-medium">{showRawRefs ? 'Göster' : 'Gizle'}</span>
                {showRawRefs ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
              </div>
            </button>

            {showRawRefs && (
              <section className="space-y-3 border-t border-border/30 bg-secondary/30 px-5 py-3 transition-all">
                {/* The whole point of this annotation platform is that the
                    kanun/bkk references shipped with the source data are
                    known to be INCOMPLETE and UNRELIABLE — the project
                    exists to produce a corrected, human-verified set. We
                    surface the upstream values here only as a starting
                    point; this banner makes sure no annotator mistakes
                    them for ground truth. */}
                <div
                  role="note"
                  data-testid="refs-source-warning"
                  className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/[0.04] px-2.5 py-1.5 text-[12px] font-medium leading-normal text-destructive"
                >
                  <AlertTriangle aria-hidden="true" className="h-3.5 w-3.5 shrink-0 translate-y-[2px]" />
                  <span>
                    <span className="font-semibold">Kaynak veriden geliyor (Eksik/Güvensiz).</span>{' '}
                    Doğrulamanız gerekir; amacımız bu listeyi insan eliyle düzeltmektir.
                  </span>
                </div>
                <RefList
                  refs={d.kanun_refs}
                  icon={BookMarked}
                  title="Kanun Bilgileri"
                  renderItem={renderKanunRef}
                />
                <RefList
                  refs={d.bkk_refs}
                  icon={BookOpen}
                  title="BKK / Tebliğ / Sirküler"
                  renderItem={renderBkkRef}
                />
              </section>
            )}
          </div>
        )}

        <article className="whitespace-pre-wrap px-5 py-5 text-[15px] leading-[1.7] text-foreground/95 font-serif">
          {cleaned}
        </article>
      </div>
    </div>
  )
}
