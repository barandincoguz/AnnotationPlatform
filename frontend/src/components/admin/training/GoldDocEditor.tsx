import { useState, useEffect } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { ConceptRowEditor } from './ConceptRowEditor'
import { DiffPreviewDialog } from '@/components/admin/DiffPreviewDialog'
import { TypedConfirmDialog } from '@/components/admin/TypedConfirmDialog'
import { useUpsertGoldDocMutation, useDeleteGoldDocMutation } from '@/api/queries/admin'
import type { Concept, GoldDocResolved } from '@/lib/adminSchemas'
import { isValidTrainingReference } from '@/lib/validateReferences'

interface Props {
  doc: GoldDocResolved
}

export function GoldDocEditor({ doc }: Props) {
  const [content, setContent] = useState(doc.content)
  const [concepts, setConcepts] = useState<Concept[]>(doc.expected_concepts)
  const [mcc, setMcc] = useState(doc.min_concept_count)
  const [diffOpen, setDiffOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const upsert = useUpsertGoldDocMutation()
  const del = useDeleteGoldDocMutation()

  useEffect(() => {
    setContent(doc.content); setConcepts(doc.expected_concepts); setMcc(doc.min_concept_count)
  }, [doc])

  const canSave = concepts.every((c) => c.kanun_no.trim() !== '' && isValidTrainingReference(c))

  const onSubmit = () => {
    upsert.mutate(
      { gold_id: doc.gold_id, content, expected_concepts: concepts, min_concept_count: mcc },
      {
        onSuccess: () => { toast.success('Gold doc kaydedildi'); setDiffOpen(false) },
        onError: () => { toast.error('Kayıt başarısız'); setDiffOpen(false) },
      },
    )
  }

  const onDelete = () => {
    del.mutate(doc.gold_id, {
      onSuccess: () => { toast.success('Tombstone uygulandı'); setDeleteOpen(false) },
      onError: () => { toast.error('Silinemedi'); setDeleteOpen(false) },
    })
  }

  return (
    <div className="space-y-4">
      <div className="font-mono text-sm">{doc.gold_id}</div>
      <div className="block">
        <label htmlFor="gd-content" className="mb-1 block text-sm">İçerik</label>
        <Textarea
          id="gd-content"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          className="min-h-32"
        />
      </div>
      <div className="space-y-2">
        <span className="block text-sm font-medium">Beklenen Kavramlar</span>
        {concepts.map((c, i) => (
          <ConceptRowEditor
            key={i}
            value={c}
            onChange={(v) => setConcepts(concepts.map((x, j) => j === i ? v : x))}
            onRemove={() => setConcepts(concepts.filter((_, j) => j !== i))}
          />
        ))}
        <Button size="sm" variant="outline" onClick={() => setConcepts([...concepts, { kanun_no: '', kanun_ad: null, madde: null, fikra: null, bent: null }])}>
          + Kavram Ekle
        </Button>
      </div>
      <label htmlFor="gd-mcc" className="block">
        <span className="mb-1 block text-sm">Min Concept Count</span>
        <Input id="gd-mcc" type="number" value={String(mcc)} onChange={(e) => setMcc(Number(e.target.value))} className="max-w-xs" />
      </label>
      <div className="flex gap-2">
        <Button variant="destructive" onClick={() => setDeleteOpen(true)}>Sil (Tombstone)</Button>
        <Button onClick={() => setDiffOpen(true)} disabled={!canSave}>Kaydet</Button>
      </div>
      <DiffPreviewDialog
        open={diffOpen}
        title="Override Onayı"
        oldValue={{ content: doc.content, expected_concepts: doc.expected_concepts, min_concept_count: doc.min_concept_count }}
        newValue={{ content, expected_concepts: concepts, min_concept_count: mcc }}
        confirmWord="OVERRIDE"
        isPending={upsert.isPending}
        onConfirm={onSubmit}
        onClose={() => setDiffOpen(false)}
      />
      <TypedConfirmDialog
        open={deleteOpen}
        title="Gold Doc Sil"
        body={<p>{doc.gold_id} kalıcı olarak tombstone&apos;lanacak.</p>}
        confirmWord="DELETE"
        isPending={del.isPending}
        onConfirm={onDelete}
        onClose={() => setDeleteOpen(false)}
      />
    </div>
  )
}
