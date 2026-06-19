import { useId } from 'react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import type { Concept } from '@/lib/adminSchemas'
import {
  getReferenceFieldDiagnostic,
  isInvalidComplexMadde,
  parseComplexMadde,
  normalizeKanunNo,
  normalizeMadde,
  normalizeIdentifier,
  normalizeKanunAdi,
  type ReferenceField,
  getLawNameByNumber,
  getLawNumberByName,
} from '@/lib/validateReferences'

interface Props {
  value: Concept
  onChange: (v: Concept) => void
  onRemove: () => void
}

export function ConceptRowEditor({ value, onChange, onRemove }: Props) {
  const uid = useId()
  const id = (field: ReferenceField) => `${uid}-${field}`
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
  const set = (k: keyof Concept, v: string | null) => onChange({ ...value, [k]: v })
  return (
    <div className="flex flex-wrap gap-2 rounded border p-2">
      <div className="min-w-32 flex-1 space-y-1">
        <Input
          aria-label="kanun_no"
          placeholder="kanun_no (zorunlu)"
          value={value.kanun_no}
          onChange={(e) => set('kanun_no', e.target.value)}
          onBlur={(e) => {
            const cleaned = normalizeKanunNo(e.target.value) ?? ''
            const autoAd = getLawNameByNumber(cleaned)
            onChange({
              ...value,
              kanun_no: cleaned,
              ...(autoAd ? { kanun_ad: autoAd } : {}),
            })
          }}
          aria-describedby={describedBy('kanun_no')}
          aria-invalid={invalidFor('kanun_no')}
        />
        {renderDiagnostic('kanun_no')}
      </div>
      <div className="min-w-32 flex-1 space-y-1">
        <Input
          aria-label="kanun_ad"
          placeholder="kanun_ad"
          value={value.kanun_ad ?? ''}
          onChange={(e) => set('kanun_ad', e.target.value || null)}
          onBlur={(e) => {
            const cleaned = normalizeKanunAdi(e.target.value)
            const autoNo = getLawNumberByName(cleaned)
            onChange({
              ...value,
              kanun_ad: cleaned,
              ...(autoNo ? { kanun_no: autoNo } : {}),
            })
          }}
          aria-describedby={describedBy('kanun_ad')}
          aria-invalid={invalidFor('kanun_ad')}
        />
        {renderDiagnostic('kanun_ad')}
      </div>
      <div className="min-w-24 flex-1 space-y-1">
        <Input
          aria-label="madde"
          placeholder="madde"
          value={value.madde ?? ''}
          onChange={(e) => set('madde', e.target.value || null)}
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
              set('madde', normalizeMadde(val))
            }
          }}
          aria-describedby={describedBy('madde')}
          aria-invalid={invalidFor('madde')}
        />
        {renderDiagnostic('madde')}
      </div>
      <div className="min-w-20 flex-1 space-y-1">
        <Input
          aria-label="fikra"
          placeholder="fikra"
          value={value.fikra ?? ''}
          onChange={(e) => set('fikra', e.target.value || null)}
          onBlur={(e) => set('fikra', normalizeIdentifier(e.target.value))}
          aria-describedby={describedBy('fikra')}
          aria-invalid={invalidFor('fikra')}
        />
        {renderDiagnostic('fikra')}
      </div>
      <div className="min-w-20 flex-1 space-y-1">
        <Input
          aria-label="bent"
          placeholder="bent"
          value={value.bent ?? ''}
          onChange={(e) => set('bent', e.target.value || null)}
          onBlur={(e) => set('bent', normalizeIdentifier(e.target.value))}
          aria-describedby={describedBy('bent')}
          aria-invalid={invalidFor('bent')}
        />
        {renderDiagnostic('bent')}
      </div>
      <Button className="self-start" variant="ghost" size="sm" onClick={onRemove}>
        Kaldır
      </Button>
    </div>
  )
}
