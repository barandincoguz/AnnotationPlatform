import { Plus, Loader2, Check, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { ReferenceCard } from './ReferenceCard'
import type { components } from '@/api/types'
import type { ApiError } from '@/api/client'
import type { DraftSaveStatus } from '@/hooks/useDraft'

type ReferenceItem = components['schemas']['ReferenceItem']

interface ReferencePanelProps {
  refs: ReferenceItem[]
  onAdd: () => void
  onUpdate: (index: number, ref: ReferenceItem) => void
  onRemove: (index: number) => void
  onSave: () => void
  onSkip: () => void
  canEdit: boolean
  isSaving: boolean
  error: ApiError | null
  draftSaveStatus: DraftSaveStatus
  isValid: boolean
}

function DraftStatusBadge({ status }: { status: DraftSaveStatus }) {
  if (status === 'saving') {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" /> Taslak kaydediliyor…
      </span>
    )
  }
  if (status === 'saved') {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        <Check className="h-3 w-3" /> Taslak kaydedildi
      </span>
    )
  }
  if (status === 'error') {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-destructive">
        <AlertCircle className="h-3 w-3" /> Taslak hatası
      </span>
    )
  }
  return null
}

export function ReferencePanel({
  refs,
  onAdd,
  onUpdate,
  onRemove,
  onSave,
  onSkip,
  canEdit,
  isSaving,
  error,
  draftSaveStatus,
  isValid,
}: ReferencePanelProps) {
  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex-1 space-y-3 overflow-auto p-3">
        {refs.length === 0 ? (
          <p className="text-sm text-muted-foreground italic">
            Henüz referans yok. &ldquo;+ Yeni Referans&rdquo; ile başlayın.
          </p>
        ) : (
          refs.map((r, i) => (
            <ReferenceCard
              key={i}
              index={i}
              value={r}
              onChange={(next) => onUpdate(i, next)}
              onRemove={() => onRemove(i)}
              disabled={!canEdit}
            />
          ))
        )}
        <Button
          type="button"
          variant="outline"
          onClick={onAdd}
          disabled={!canEdit}
          className="w-full"
        >
          <Plus className="mr-1 h-4 w-4" /> Yeni Referans
        </Button>
      </div>
      <Separator />
      <footer className="space-y-2 p-3">
        <div className="flex items-center justify-between">
          <DraftStatusBadge status={draftSaveStatus} />
        </div>
        {error && (
          <p className="text-sm text-destructive" role="alert">
            {error.message}
          </p>
        )}
        {!isValid && refs.length > 0 && (
          <p className="text-xs text-muted-foreground">
            Her referans için <strong>source_text</strong> ve en az bir tane{' '}
            <strong>kanun_no</strong> veya <strong>kanun_ad</strong> doldurulmalı.
          </p>
        )}
        <div className="flex items-center justify-end gap-2">
          <Button type="button" variant="outline" onClick={onSkip} disabled={!canEdit || isSaving}>
            Atla
          </Button>
          <Button type="button" onClick={onSave} disabled={!canEdit || isSaving || !isValid}>
            {isSaving ? 'Kaydediliyor…' : 'Sakla'}
          </Button>
        </div>
      </footer>
    </div>
  )
}
