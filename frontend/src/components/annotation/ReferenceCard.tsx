import { X, Quote, AlertCircle, ChevronUp } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { components } from '@/api/types'
import {
  getReferenceFieldDiagnostic,
  isInvalidComplexMadde,
  parseComplexMadde,
  normalizeKanunNo,
  normalizeMadde,
  normalizeIdentifier,
  normalizeKanunAdi,
  isSourceTextInDoc,
  type ReferenceField,
  getLawNameByNumber,
  getLawNumberByName,
} from '@/lib/validateReferences'

type ReferenceItem = components['schemas']['ReferenceItem']

interface ReferenceCardProps {
  index: number
  value: ReferenceItem
  docText?: string
  onChange: (next: ReferenceItem) => void
  onRemove: () => void
  disabled: boolean
  isExpanded: boolean
  onExpand: () => void
}

function set<K extends keyof ReferenceItem>(prev: ReferenceItem, key: K, v: string): ReferenceItem {
  return { ...prev, [key]: v === '' ? (key === 'source_text' ? '' : null) : v }
}

export function ReferenceCard({
  index,
  value,
  docText = '',
  onChange,
  onRemove,
  disabled,
  isExpanded,
  onExpand,
}: ReferenceCardProps) {
  const id = (k: string) => `ref-${index}-${k}`
  const isSourceInDoc = isSourceTextInDoc(value.source_text, docText)
  const diagnostics: Record<ReferenceField, ReturnType<typeof getReferenceFieldDiagnostic>> = {
    kanun_no: getReferenceFieldDiagnostic('kanun_no', value.kanun_no, value),
    kanun_ad: getReferenceFieldDiagnostic('kanun_ad', value.kanun_ad, value),
    madde: getReferenceFieldDiagnostic('madde', value.madde, value),
    fikra: getReferenceFieldDiagnostic('fikra', value.fikra, value),
    bent: getReferenceFieldDiagnostic('bent', value.bent, value),
  }
  const diagnosticFor = (field: ReferenceField) => diagnostics[field]
  const diagnosticId = (field: ReferenceField) => `${id(field)}-diagnostic`
  const describedBy = (field: ReferenceField) =>
    diagnosticFor(field) ? diagnosticId(field) : undefined
  const invalidFor = (field: ReferenceField) =>
    diagnosticFor(field)?.level === 'error' ? true : undefined
  const renderDiagnostic = (field: ReferenceField) => {
    const diagnostic = diagnosticFor(field)
    if (!diagnostic) return null
    return (
      <p
        id={diagnosticId(field)}
        aria-live="polite"
        className="text-xs text-destructive"
      >
        {diagnostic.message}
      </p>
    )
  }

  const hasFieldError = Object.values(diagnostics).some(
    (diagnostic) => diagnostic?.level === 'error',
  )
  const isCardInvalid =
    hasFieldError ||
    !value.source_text?.trim() ||
    (!value.kanun_no?.trim() && !value.kanun_ad?.trim())

  if (!isExpanded) {
    const summaryParts = []
    if (value.kanun_no) summaryParts.push(`Kanun No: ${value.kanun_no}`)
    if (value.kanun_ad) summaryParts.push(value.kanun_ad)
    if (value.madde) summaryParts.push(`Md: ${value.madde}`)
    if (value.fikra) summaryParts.push(`Fık: ${value.fikra}`)
    if (value.bent) summaryParts.push(`Bnt: ${value.bent}`)

    const summaryText = summaryParts.join(' · ') || 'Yeni Boş Referans'
    const quoteSnippet = value.source_text
      ? value.source_text.length > 45
        ? `"${value.source_text.substring(0, 45)}..."`
        : `"${value.source_text}"`
      : 'Metinden alıntı girilmedi'

    return (
      <Card
        onClick={onExpand}
        className={cn(
          'relative overflow-hidden cursor-pointer transition-all hover:bg-secondary/15 shadow-sm border',
          isCardInvalid
            ? 'border-destructive/30 bg-destructive/[0.01] hover:border-destructive/50'
            : 'border-border/60 hover:border-border/80',
        )}
      >
        <span
          aria-hidden
          className={cn(
            'absolute inset-y-0 left-0 w-1',
            isCardInvalid ? 'bg-destructive/50' : 'bg-accent2/50',
          )}
        />
        <div className="flex items-center justify-between gap-3 px-3 py-2 pl-5">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <span
              className={cn(
                'inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full font-mono text-[10px] font-bold tabular-nums',
                isCardInvalid ? 'bg-destructive/10 text-destructive' : 'bg-accent2/10 text-accent2',
              )}
            >
              {index + 1}
            </span>
            <div className="flex flex-col min-w-0 flex-1 leading-tight">
              <span className="font-mono text-[11px] font-bold text-foreground/90 truncate">
                {summaryText}
              </span>
              <span
                className={cn(
                  'font-serif text-[11px] italic truncate',
                  isCardInvalid ? 'text-destructive/80' : 'text-muted-foreground',
                )}
              >
                {quoteSnippet}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            {isCardInvalid && (
              <AlertCircle
                className="h-4 w-4 text-destructive shrink-0"
                aria-label="Geçersiz alanlar var"
              />
            )}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation()
                onRemove()
              }}
              disabled={disabled}
              aria-label="sil"
              className="h-7 w-7 p-0 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </Card>
    )
  }

  return (
    <Card
      className={cn(
        'relative overflow-hidden transition-shadow hover:shadow-md border',
        isCardInvalid ? 'border-destructive/30 bg-destructive/[0.005]' : 'border-border/70',
      )}
    >
      {/* Left accent ribbon — a small color seal making the card feel
          like a numbered citation rather than a generic form. */}
      <span
        aria-hidden
        className={cn(
          'absolute inset-y-0 left-0 w-1',
          isCardInvalid ? 'bg-destructive/70' : 'bg-accent2/70',
        )}
      />
      <CardContent className="space-y-5 p-5 pl-6">
        <div className="flex items-center justify-between gap-2 border-b border-border/30 pb-3">
          <button
            type="button"
            onClick={onExpand}
            className="flex items-center gap-2.5 cursor-pointer select-none group/hdr flex-1 min-w-0 text-left focus-visible:outline-none"
            title="Daraltmak için tıklayın"
          >
            <span
              className={cn(
                'inline-flex h-7 w-7 items-center justify-center rounded-full font-mono text-[12px] font-bold tabular-nums transition-colors',
                isCardInvalid
                  ? 'bg-destructive/15 text-destructive group-hover/hdr:bg-destructive/25'
                  : 'bg-accent2/15 text-accent2 group-hover/hdr:bg-accent2/25',
              )}
            >
              {index + 1}
            </span>
            <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground group-hover/hdr:text-foreground transition-colors truncate">
              Referans
            </span>
            <ChevronUp className="h-3.5 w-3.5 text-muted-foreground/60 group-hover/hdr:text-foreground transition-colors shrink-0" />
          </button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onRemove}
            disabled={disabled}
            aria-label="sil"
            className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
          >
            <X />
          </Button>
        </div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-4">
          <div className="space-y-1.5">
            <Label htmlFor={id('kanun_no')}>Kanun No</Label>
            <Input
              id={id('kanun_no')}
              value={value.kanun_no ?? ''}
              onChange={(e) => onChange(set(value, 'kanun_no', e.target.value))}
              onBlur={(e) => {
                const cleaned = normalizeKanunNo(e.target.value)
                let next = set(value, 'kanun_no', cleaned ?? '')
                const autoAd = getLawNameByNumber(cleaned)
                if (autoAd) {
                  next = set(next, 'kanun_ad', autoAd)
                }
                onChange(next)
              }}
              aria-describedby={describedBy('kanun_no')}
              aria-invalid={invalidFor('kanun_no')}
              disabled={disabled}
            />
            {renderDiagnostic('kanun_no')}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={id('kanun_ad')}>Kanun Adı</Label>
            <Input
              id={id('kanun_ad')}
              value={value.kanun_ad ?? ''}
              onChange={(e) => onChange(set(value, 'kanun_ad', e.target.value))}
              onBlur={(e) => {
                const cleaned = normalizeKanunAdi(e.target.value)
                let next = set(value, 'kanun_ad', cleaned ?? '')
                const autoNo = getLawNumberByName(cleaned)
                if (autoNo) {
                  next = set(next, 'kanun_no', autoNo)
                }
                onChange(next)
              }}
              aria-describedby={describedBy('kanun_ad')}
              aria-invalid={invalidFor('kanun_ad')}
              disabled={disabled}
            />
            {renderDiagnostic('kanun_ad')}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={id('madde')}>Madde</Label>
            <Input
              id={id('madde')}
              value={value.madde ?? ''}
              onChange={(e) => onChange(set(value, 'madde', e.target.value))}
              onBlur={(e) => {
                const val = e.target.value
                const parsed = parseComplexMadde(val)
                if (parsed) {
                  onChange({
                    ...value,
                    madde: parsed.madde,
                    fikra: parsed.fikra ?? value.fikra ?? null,
                    bent: parsed.bent ?? value.bent ?? null,
                  })
                } else if (!isInvalidComplexMadde(val)) {
                  onChange(set(value, 'madde', normalizeMadde(val) ?? ''))
                }
              }}
              aria-describedby={describedBy('madde')}
              aria-invalid={invalidFor('madde')}
              disabled={disabled}
            />
            {renderDiagnostic('madde')}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={id('fikra')}>Fıkra</Label>
            <Input
              id={id('fikra')}
              value={value.fikra ?? ''}
              onChange={(e) => onChange(set(value, 'fikra', e.target.value))}
              onBlur={(e) => {
                const cleaned = normalizeIdentifier(e.target.value)
                onChange(set(value, 'fikra', cleaned ?? ''))
              }}
              aria-describedby={describedBy('fikra')}
              aria-invalid={invalidFor('fikra')}
              disabled={disabled}
            />
            {renderDiagnostic('fikra')}
          </div>
          <div className="space-y-1.5 col-span-2">
            <Label htmlFor={id('bent')}>Bent</Label>
            <Input
              id={id('bent')}
              value={value.bent ?? ''}
              onChange={(e) => onChange(set(value, 'bent', e.target.value))}
              onBlur={(e) => {
                const cleaned = normalizeIdentifier(e.target.value)
                onChange(set(value, 'bent', cleaned ?? ''))
              }}
              aria-describedby={describedBy('bent')}
              aria-invalid={invalidFor('bent')}
              disabled={disabled}
            />
            {renderDiagnostic('bent')}
          </div>
        </div>
        <div
          className={cn(
            'space-y-1.5 rounded-md border p-3',
            isCardInvalid
              ? 'border-destructive/20 bg-destructive/[0.02]'
              : 'border-accent/20 bg-accent/[0.04]',
          )}
        >
          <Label
            htmlFor={id('source')}
            className={cn(
              'flex items-center gap-1.5',
              isCardInvalid ? 'text-destructive' : 'text-accent',
            )}
          >
            <Quote aria-hidden="true" className="h-3 w-3" />
            Metinden Alıntı
          </Label>
          <Textarea
            id={id('source')}
            value={value.source_text}
            onChange={(e) => onChange({ ...value, source_text: e.target.value })}
            disabled={disabled}
            rows={3}
            required
            className={cn(
              'bg-card focus-visible:ring-1 focus-visible:ring-offset-0',
              isCardInvalid
                ? 'border-destructive/30 focus-visible:border-destructive focus-visible:ring-destructive'
                : 'border-accent/30 focus-visible:border-accent focus-visible:ring-accent',
            )}
          />
          {!isSourceInDoc && value.source_text && (
            <p className="mt-1.5 flex items-center gap-1.5 text-xs text-warning" role="status" aria-live="polite">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" />
              Alıntı metni özelge gövdesinde bulunamadı. Lütfen kopyalamanın doğru yapıldığından emin olun.
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
