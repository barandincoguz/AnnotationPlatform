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
    <div className="flex items-baseline gap-2">
      <Icon aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-muted-foreground/80 translate-y-[2px]" />
      <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
        {label}
      </span>
      <span className="font-medium tabular-nums text-foreground">{value}</span>
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
    <section className="space-y-2">
      <div className="flex items-baseline gap-2">
        <Icon aria-hidden="true" className="h-4 w-4 text-accent" />
        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
          {title}
        </span>
        <span className="font-mono text-[11px] font-bold tabular-nums text-foreground/80">
          {refs.length}
        </span>
      </div>
      <ol className="space-y-1.5 pl-1">
        {refs.map((ref) => (
          <li
            key={ref.seq}
            className="flex items-baseline gap-2.5 rounded-md border border-border/50 bg-card/60 px-3 py-2 text-[14px]"
          >
            <span className="font-mono text-[11px] font-bold tabular-nums text-accent">
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
    <header className="space-y-3 border-b border-border/60 bg-card/60 px-5 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div className="space-y-1">
          <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
            Doküman Kimliği
          </div>
          <div
            title="Doküman kimliği (evrakOid)"
            className="font-mono text-xl font-bold leading-none tracking-tight text-foreground select-all"
          >
            {d.document_id}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {d.estimated_difficulty && (
            <span
              className={cn(
                'inline-flex items-center rounded-full border px-2.5 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.18em]',
                difficultyTint(d.estimated_difficulty),
              )}
            >
              {d.estimated_difficulty}
            </span>
          )}
          {d.word_count > 0 && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              <AlignLeft className="h-3 w-3" />
              {TR_FORMATTER.format(d.word_count)} kelime
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-[13px] sm:grid-cols-2">
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
        <div className="space-y-1 border-t border-border/40 pt-3">
          <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
            Konu
          </div>
          <p className="text-[15px] font-semibold leading-snug text-foreground">
            {d.konu}
          </p>
        </div>
      )}
    </header>
  )
}

export function DocViewer({ docId }: DocViewerProps) {
  const q = useDoc(docId)
  if (q.isPending) {
    return <div className="p-4 text-[15px] text-muted-foreground">Yükleniyor…</div>
  }
  if (q.error || !q.data) {
    return <div className="p-4 text-[15px] text-destructive">Doküman yüklenemedi.</div>
  }
  const d = q.data
  const cleaned = normalizeOzelgeText(d.pdf_text)
  const hasRefs = d.kanun_refs.length > 0 || d.bkk_refs.length > 0

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <Header d={d} />

      <div className="flex-1 overflow-auto">
        {hasRefs && (
          <section className="space-y-4 border-b border-border/40 bg-secondary/30 px-5 py-4">
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
              className="flex items-start gap-2.5 rounded-md border border-destructive/40 bg-destructive/[0.07] px-3 py-2.5 text-[13px] font-medium leading-snug text-destructive"
            >
              <AlertTriangle aria-hidden="true" className="h-4 w-4 shrink-0 translate-y-[1px]" />
              <span>
                <span className="font-semibold">Kaynak veriden geliyor.</span>{' '}
                Bu referanslar eksik ve güvenilir değildir — doğrulamanız
                gerekir. Anotasyon platformunun varlık sebebi tam olarak
                bu listeyi insan eliyle düzeltmektir.
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

        <article className="whitespace-pre-wrap px-5 py-5 text-[15px] leading-[1.7] text-foreground/95 font-serif">
          {cleaned}
        </article>
      </div>
    </div>
  )
}
