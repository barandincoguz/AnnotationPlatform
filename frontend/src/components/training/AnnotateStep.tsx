import { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ReferenceCard } from '@/components/annotation/ReferenceCard'
import { useTrainingStore } from '@/stores/trainingStore'
import {
  areAllTrainingReferencesValid,
  emptyReferenceItem,
  checkAndRemoveDuplicateReferences,
} from '@/lib/validateReferences'
import { toast } from 'sonner'
import { formatConcept } from '@/lib/formatTrainingConcept'
import type { components } from '@/api/types'

type ReferenceItem = components['schemas']['ReferenceItem']

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

  const refs = currentDoc ? (docRefs[currentDoc.gold_id] ?? []) : []
  const [activeCardIndex, setActiveCardIndex] = useState<number | null>(0)
  const prevLengthRef = useRef(refs.length)

  // Auto-expand newly added reference cards
  useEffect(() => {
    if (refs.length > prevLengthRef.current) {
      setActiveCardIndex(refs.length - 1)
    }
    prevLengthRef.current = refs.length
  }, [refs.length])

  const handleExpand = (index: number) => {
    setActiveCardIndex((prev) => (prev === index ? null : index))
  }

  if (!currentDoc) {
    return <p className="text-sm text-muted-foreground">Doküman bulunamadı.</p>
  }

  const allValid = areAllTrainingReferencesValid(refs)

  const updateRef = (idx: number, next: ReferenceItem) => {
    const updated = [...refs]
    updated[idx] = next
    setDocRefs(currentDoc.gold_id, updated)
  }
  const removeRef = (idx: number) => setDocRefs(currentDoc.gold_id, refs.filter((_, i) => i !== idx))
  const addRef = () => setDocRefs(currentDoc.gold_id, [...refs, emptyReferenceItem()])

  if (resultShown?.kind === 'doc' && resultShown.goldId === currentDoc.gold_id) {
    const result = docResults[currentDoc.gold_id]
    if (!result) return null
    const isLast = docIndex === 2
    return (
      <section aria-labelledby="doc-result-heading">
        <h2 ref={headingRef} tabIndex={-1} id="doc-result-heading" className="text-xl font-semibold focus:outline-none">
          Doküman {docIndex + 1} tamamlandı
        </h2>
        <div
          role="status"
          aria-live="polite"
          className={cn(
            'mt-4 rounded-md border p-4 text-sm',
            result.passed
              ? 'bg-success/5 border-success/30'
              : 'bg-destructive/5 border-destructive/30',
          )}
        >
          <p>Eşleşme: <strong>{result.matched_count} / {result.expected_count}</strong></p>
          <p className={cn('mt-1', result.passed ? 'text-success' : 'text-destructive')}>
            Durum: <strong>{result.passed ? 'Geçti' : 'Geçemedi'}</strong>
          </p>
        </div>
        <div
          role="region"
          aria-label="Beklenen anotasyonlar"
          className="mt-3 rounded-md border bg-muted/40 p-4 text-sm"
        >
          <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
            Geri bildirim
          </p>
          <p className="mb-2 font-medium">
            Beklenen anotasyonlar:
          </p>
          <ol className="list-decimal space-y-1 pl-5">
            {result.expected_concepts.map((concept, index) => (
              <li key={index}>{formatConcept(concept)}</li>
            ))}
          </ol>
        </div>
        <div className="mt-6">
          <Button onClick={onAdvance}>
            {isLast ? 'Sonuçları gör' : `Sonraki: Doküman ${docIndex + 2}`}
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
            docText={currentDoc.content}
            onChange={(next) => updateRef(i, next)}
            onRemove={() => removeRef(i)}
            disabled={isSubmitting}
            isExpanded={activeCardIndex === i}
            onExpand={() => handleExpand(i)}
          />
        ))}
        <Button onClick={addRef} variant="outline" size="sm" disabled={isSubmitting}>
          + Yeni Referans
        </Button>
      </section>
      <div className="mt-6">
        <Button
          onClick={() => {
            const { list: cleanedRefs, hasDuplicates } = checkAndRemoveDuplicateReferences(refs)
            if (hasDuplicates) {
              toast.warning('Yinelenen anotasyon silindi.')
              setDocRefs(currentDoc.gold_id, cleanedRefs)
              onSubmit(currentDoc.gold_id, cleanedRefs)
            } else {
              onSubmit(currentDoc.gold_id, refs)
            }
          }}
          disabled={isSubmitting || !allValid}
        >
          {isSubmitting ? 'Gönderiliyor...' : 'Gönder ve devam et'}
        </Button>
      </div>
    </section>
  )
}
