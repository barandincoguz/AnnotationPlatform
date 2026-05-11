import { useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { ReferenceCard } from '@/components/annotation/ReferenceCard'
import { useTrainingStore } from '@/stores/trainingStore'
import type { components } from '@/api/types'

type ReferenceItem = components['schemas']['ReferenceItem']

function emptyRef(): ReferenceItem {
  return { kanun_no: null, kanun_ad: null, madde: null, fikra: null, bent: null, source_text: '' }
}

function isTrainingReferenceValid(r: ReferenceItem): boolean {
  if (!r.source_text || r.source_text.trim().length === 0) return false
  if (!r.kanun_no || r.kanun_no.trim().length === 0) return false
  return true
}

interface AnnotateStepProps {
  onSubmit: (goldId: string, references: ReferenceItem[]) => void
  onAdvance: () => void
  isSubmitting: boolean
}

export function AnnotateStep({ onSubmit, onAdvance, isSubmitting }: AnnotateStepProps) {
  const docIndex = useTrainingStore((s) => s.docIndex)
  const goldDocs = useTrainingStore((s) => s.goldDocs)
  const docRefs = useTrainingStore((s) => s.docRefs)
  const docResults = useTrainingStore((s) => s.docResults)
  const resultShown = useTrainingStore((s) => s.resultShown)
  const setDocRefs = useTrainingStore((s) => s.setDocRefs)
  const headingRef = useRef<HTMLHeadingElement | null>(null)

  useEffect(() => {
    headingRef.current?.focus()
  }, [resultShown, docIndex])

  const currentDoc = goldDocs[docIndex]
  if (!currentDoc) {
    return <p className="text-sm text-muted-foreground">Doküman bulunamadı.</p>
  }
  const refs = docRefs[currentDoc.gold_id] ?? []
  const allValid = refs.every(isTrainingReferenceValid)

  const updateRef = (idx: number, next: ReferenceItem) => {
    const updated = [...refs]
    updated[idx] = next
    setDocRefs(currentDoc.gold_id, updated)
  }
  const removeRef = (idx: number) => setDocRefs(currentDoc.gold_id, refs.filter((_, i) => i !== idx))
  const addRef = () => setDocRefs(currentDoc.gold_id, [...refs, emptyRef()])

  if (resultShown?.kind === 'doc' && resultShown.goldId === currentDoc.gold_id) {
    const result = docResults[currentDoc.gold_id]
    if (!result) return null
    const isLast = docIndex === 2
    return (
      <section aria-labelledby="doc-result-heading">
        <h2 ref={headingRef} tabIndex={-1} id="doc-result-heading" className="text-xl font-semibold focus:outline-none">
          Doküman {docIndex + 1} tamamlandı
        </h2>
        <div role="status" aria-live="polite" className="mt-4 rounded-md border bg-card p-4 text-sm">
          <p>Eşleşme: <strong>{result.matched_count} / {result.expected_count}</strong></p>
          <p className="mt-1">Durum: <strong>{result.passed ? 'Geçti' : 'Geçemedi'}</strong></p>
        </div>
        <div className="mt-6">
          <Button onClick={onAdvance}>
            {isLast ? 'Sonuçları Gör ▸' : `Sonraki: Doküman ${docIndex + 2} ▸`}
          </Button>
        </div>
      </section>
    )
  }

  return (
    <section aria-labelledby="doc-heading">
      <h2 ref={headingRef} tabIndex={-1} id="doc-heading" className="text-xl font-semibold focus:outline-none">
        Doküman {docIndex + 1}
      </h2>
      <article className="mt-4 rounded-md border bg-card p-4">
        {currentDoc.content.split(/\n\s*\n/).map((para, i) => (
          <p key={i} className="mb-2 text-sm leading-relaxed last:mb-0">{para}</p>
        ))}
      </article>
      <section aria-labelledby="refs-heading" className="mt-6 space-y-3">
        <h3 id="refs-heading" className="text-sm font-medium">
          Referanslar <span className="text-muted-foreground">(kanun atfı yoksa boş bırakabilirsin)</span>
        </h3>
        {refs.map((r, i) => (
          <ReferenceCard
            key={i}
            index={i}
            value={r}
            onChange={(next) => updateRef(i, next)}
            onRemove={() => removeRef(i)}
            disabled={isSubmitting}
          />
        ))}
        <Button onClick={addRef} variant="outline" size="sm" disabled={isSubmitting}>
          + Yeni Referans
        </Button>
      </section>
      <div className="mt-6">
        <Button onClick={() => onSubmit(currentDoc.gold_id, refs)} disabled={isSubmitting || !allValid}>
          {isSubmitting ? 'Gönderiliyor...' : 'Submit & Sonraki ▸'}
        </Button>
      </div>
    </section>
  )
}
