import { AlertTriangle, ArrowLeft, Check, Plus, ShieldCheck } from 'lucide-react'

import type { AuditDiscrepancy, PreAuditResult } from '@/api/queries/annotations'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'

const BUCKET_LABEL: Record<string, string> = {
  RED: 'Kanun veya madde listesi uyuşmuyor',
  YELLOW: 'Referans ayrıntıları uyuşmuyor',
  QUARANTINE: 'Teknik inceleme gerekiyor',
}

const KIND_LABEL: Record<AuditDiscrepancy['kind'], string> = {
  model_only: 'Model buldu, sizde yok',
  human_only: 'Sizde var, model bulamadı',
  detail_mismatch: 'Ayrıntı farkı (fıkra / bent / alıntı)',
}

const FIELD_LABEL: Record<string, string> = {
  fikra: 'fıkra',
  bent: 'bent',
  source_text: 'metinden alıntı',
}

type ReferenceLike = Record<string, string> | null | undefined

/** Stable id for a discrepancy: highlight target + "already accepted" key. */
export function discrepancyKey(discrepancy: AuditDiscrepancy): string {
  const reference = discrepancy.model_reference ?? discrepancy.human_reference
  return [
    discrepancy.kind,
    discrepancy.kanun_no,
    discrepancy.madde,
    reference?.fikra ?? '',
    reference?.bent ?? '',
  ].join(':')
}

function referenceLabel(reference: ReferenceLike): string {
  if (!reference) return '—'
  const law = reference.kanun_ad || reference.kanun_no || 'Kanun belirtilmemiş'
  const article = reference.madde ? ` m.${reference.madde}` : ''
  const fikra = reference.fikra ? `/${reference.fikra}` : ''
  const bent = reference.bent ? `-${reference.bent}` : ''
  return `${law}${article}${fikra}${bent}`
}

interface QualityAuditPanelProps {
  result: PreAuditResult
  acceptedKeys: ReadonlySet<string>
  staleNotice?: string | null
  isCompleting: boolean
  onAccept: (discrepancy: AuditDiscrepancy) => void
  onHover: (highlightId: string | null) => void
  onComplete: () => void
  onOverride: () => void
  onBackToEdit: () => void
}

export function QualityAuditPanel({
  result,
  acceptedKeys,
  staleNotice = null,
  isCompleting,
  onAccept,
  onHover,
  onComplete,
  onOverride,
  onBackToEdit,
}: QualityAuditPanelProps) {
  const bucket = result.bucket ?? ''
  return (
    <div className="flex h-full min-w-0 flex-col overflow-hidden">
      <header className="space-y-2 border-b border-border/60 bg-card/60 px-5 py-3">
        <h2 className="font-display text-[1.0625rem] font-bold tracking-tight text-foreground">
          Model Karşılaştırma & Kalite Denetimi
        </h2>
        <p
          role="note"
          className="flex items-start gap-2 rounded-md border border-warning/30 bg-warning/[0.07] px-2.5 py-1.5 text-[12px] font-medium leading-normal text-foreground/90"
        >
          <AlertTriangle aria-hidden="true" className="h-3.5 w-3.5 shrink-0 translate-y-[2px] text-warning" />
          <span>
            ⚠️ Unutmayınız: Model yanılıyor olabilir. Lütfen aşağıdaki tespitleri kaynak
            metne göre değerlendiriniz.
          </span>
        </p>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              'inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.12em]',
              bucket === 'RED'
                ? 'border-destructive/30 bg-destructive/10 text-destructive'
                : 'border-warning/30 bg-warning/10 text-warning',
            )}
          >
            {bucket}
          </span>
          <span className="text-[13px] font-semibold text-foreground/90">
            {BUCKET_LABEL[bucket] ?? 'Belgeyi kontrol edin'}
          </span>
        </div>
        {staleNotice && (
          <p
            role="status"
            className="rounded-md border border-accent/30 bg-accent/[0.07] px-2.5 py-1.5 text-[12px] font-medium leading-normal text-foreground/90"
          >
            {staleNotice}
          </p>
        )}
      </header>

      <div className="min-w-0 flex-1 space-y-2 overflow-auto px-5 py-3">
        {(result.discrepancies ?? []).map((discrepancy) => {
          const key = discrepancyKey(discrepancy)
          const model = discrepancy.model_reference
          const accepted = acceptedKeys.has(key)
          const canAccept = Boolean(model?.source_text)
          return (
            <section
              key={key}
              data-testid={`audit-row-${key}`}
              onMouseEnter={() => onHover(key)}
              onMouseLeave={() => onHover(null)}
              onFocus={() => onHover(key)}
              onBlur={() => onHover(null)}
              className="space-y-1.5 rounded-md border border-border/60 bg-card/45 px-3 py-2"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">
                  {KIND_LABEL[discrepancy.kind]}
                </span>
                {discrepancy.match_mode === null && model && (
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-destructive">
                    <AlertTriangle aria-hidden="true" className="h-3 w-3" />
                    Alıntı doküman metninde bulunamadı
                  </span>
                )}
              </div>

              {model && (
                <p className="text-[13px] leading-snug text-foreground/90">
                  <span className="font-semibold">Model:</span> {referenceLabel(model)}
                </p>
              )}
              {discrepancy.human_reference && (
                <p className="text-[13px] leading-snug text-foreground/90">
                  <span className="font-semibold">Sizde:</span>{' '}
                  {referenceLabel(discrepancy.human_reference)}
                </p>
              )}
              {(discrepancy.field_diffs ?? []).length > 0 && (
                <p className="text-[12px] text-muted-foreground">
                  Farklı alanlar:{' '}
                  {(discrepancy.field_diffs ?? [])
                    .map((field) => FIELD_LABEL[field] ?? field)
                    .join(', ')}
                </p>
              )}
              {model?.source_text && (
                <blockquote className="border-l-2 border-warning/40 pl-2 font-serif text-[12px] leading-snug text-foreground/80">
                  {model.source_text}
                </blockquote>
              )}

              {canAccept && (
                <Button
                  type="button"
                  size="sm"
                  variant={accepted ? 'outline' : 'default'}
                  disabled={accepted || isCompleting}
                  onClick={() => onAccept(discrepancy)}
                  className="min-w-0 max-w-full whitespace-normal px-2 text-center leading-tight"
                >
                  {accepted ? <Check /> : <Plus />}
                  {accepted ? 'Eklendi' : 'Model Önerisini Listeme Ekle'}
                </Button>
              )}
            </section>
          )
        })}
      </div>

      <Separator />
      <footer className="space-y-2 bg-card/60 p-5">
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={isCompleting}
          onClick={onOverride}
          className="w-full min-w-0 whitespace-normal px-2 text-center leading-tight"
        >
          <ShieldCheck />
          Benim Etiketim Doğru, Yine de Tamamla
        </Button>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={isCompleting}
            onClick={onBackToEdit}
            className="min-w-0 max-w-full whitespace-normal px-2 text-center leading-tight"
          >
            <ArrowLeft />
            Düzenlemeye Geri Dön
          </Button>
          <Button
            type="button"
            size="sm"
            variant="success"
            disabled={isCompleting}
            onClick={onComplete}
            className="min-w-0 max-w-full whitespace-normal px-2 text-center leading-tight"
          >
            <Check />
            Tamamla
          </Button>
        </div>
      </footer>
    </div>
  )
}
