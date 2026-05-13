import { useState, useEffect } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DiffPreviewDialog } from '@/components/admin/DiffPreviewDialog'
import { TypedConfirmDialog } from '@/components/admin/TypedConfirmDialog'
import { useUpsertQuizMutation, useDeleteQuizMutation } from '@/api/queries/admin'
import type { QuizQuestion } from '@/lib/adminSchemas'

interface Props {
  q: QuizQuestion
}

export function QuizEditor({ q }: Props) {
  const [text, setText] = useState(q.text)
  const [choices, setChoices] = useState<string[]>(q.choices)
  const [correct, setCorrect] = useState(q.correct_choice_idx)
  const [diffOpen, setDiffOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const upsert = useUpsertQuizMutation()
  const del = useDeleteQuizMutation()

  useEffect(() => {
    setText(q.text); setChoices(q.choices); setCorrect(q.correct_choice_idx)
  }, [q])

  const canSave = text.trim() !== '' && choices.every((c) => c.trim() !== '') && [0, 1, 2, 3].includes(correct)

  const onSubmit = () => {
    upsert.mutate(
      { question_id: q.id, text, choices, correct_choice_idx: correct },
      {
        onSuccess: () => { toast.success('Quiz güncellendi'); setDiffOpen(false) },
        onError: () => { toast.error('Kayıt başarısız'); setDiffOpen(false) },
      },
    )
  }

  const onDelete = () => {
    del.mutate(q.id, {
      onSuccess: () => { toast.success('Tombstone uygulandı'); setDeleteOpen(false) },
      onError: () => { toast.error('Silinemedi'); setDeleteOpen(false) },
    })
  }

  return (
    <div className="space-y-4">
      <div className="font-mono text-sm">{q.id}</div>
      <label className="block">
        <span className="mb-1 block text-sm">Soru metni</span>
        <textarea aria-label="Soru metni" value={text} onChange={(e) => setText(e.target.value)}
          className="min-h-24 w-full rounded border p-2 text-sm" />
      </label>
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Şıklar (4)</legend>
        {(['A', 'B', 'C', 'D'] as const).map((label, i) => (
          <div key={i} className="flex items-center gap-2">
            <input type="radio" id={`correct-${i}`} name="correct" checked={correct === i}
              onChange={() => setCorrect(i)} aria-label={`Doğru cevap ${label}`} />
            <Input aria-label={`Şık ${label}`} value={choices[i] ?? ''}
              onChange={(e) => setChoices(choices.map((c, j) => j === i ? e.target.value : c))} />
          </div>
        ))}
      </fieldset>
      <div className="flex gap-2">
        <Button variant="destructive" onClick={() => setDeleteOpen(true)}>Sil (Tombstone)</Button>
        <Button onClick={() => setDiffOpen(true)} disabled={!canSave}>Kaydet</Button>
      </div>
      <DiffPreviewDialog
        open={diffOpen}
        title="Quiz Override Onayı"
        oldValue={{ text: q.text, choices: q.choices, correct_choice_idx: q.correct_choice_idx }}
        newValue={{ text, choices, correct_choice_idx: correct }}
        confirmWord="OVERRIDE"
        isPending={upsert.isPending}
        onConfirm={onSubmit}
        onClose={() => setDiffOpen(false)}
      />
      <TypedConfirmDialog
        open={deleteOpen}
        title="Quiz Sorusu Sil"
        body={<p>{q.id} kalıcı olarak tombstone&apos;lanacak.</p>}
        confirmWord="DELETE"
        isPending={del.isPending}
        onConfirm={onDelete}
        onClose={() => setDeleteOpen(false)}
      />
    </div>
  )
}
