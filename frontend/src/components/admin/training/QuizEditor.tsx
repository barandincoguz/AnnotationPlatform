import { useState, useEffect } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
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
      <div className="block">
        <label htmlFor="qe-text" className="mb-1 block text-sm">Soru metni</label>
        <Textarea id="qe-text" value={text} onChange={(e) => setText(e.target.value)}
          className="min-h-24" />
      </div>
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Şıklar (4)</legend>
        <RadioGroup
          value={String(correct)}
          onValueChange={(v) => setCorrect(Number(v))}
          className="space-y-2 gap-0"
        >
          {(['A', 'B', 'C', 'D'] as const).map((label, i) => (
            <div key={i} className="flex items-center gap-2">
              <RadioGroupItem id={`correct-${i}`} value={String(i)} aria-label={`Doğru cevap ${label}`} />
              <Input aria-label={`Şık ${label}`} value={choices[i] ?? ''}
                onChange={(e) => setChoices(choices.map((c, j) => j === i ? e.target.value : c))} />
            </div>
          ))}
        </RadioGroup>
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
