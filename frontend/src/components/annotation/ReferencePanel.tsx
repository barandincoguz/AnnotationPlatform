import { Plus, Loader2, Check, AlertCircle, Undo2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
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
  onComplete: () => void
  canEdit: boolean
  isSaving: boolean
  isCompleting: boolean
  error: ApiError | null
  draftSaveStatus: DraftSaveStatus
  isValid: boolean
  /** True when a shared annotation row exists for this document. */
  hasAnnotation: boolean
  /** Singleton completion flag from the annotation row. */
  isCompleted: boolean
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
  onComplete,
  canEdit,
  isSaving,
  isCompleting,
  error,
  draftSaveStatus,
  isValid,
  hasAnnotation,
  isCompleted,
}: ReferencePanelProps) {
  const completeDisabled =
    !canEdit ||
    isSaving ||
    isCompleting ||
    // Refuse to lock in an invalid state when finalizing; allow the reverse
    // direction (Geri Al) regardless so users can recover from a mistaken
    // completion even if the editor currently shows invalid refs.
    (!isCompleted && !isValid)

  const completeLabel = isCompleting
    ? isCompleted
      ? 'Geri alınıyor…'
      : 'Tamamlanıyor…'
    : isCompleted
      ? 'Geri Al'
      : 'Tamamla'

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
          {hasAnnotation && isCompleted && (
            <span className="inline-flex items-center gap-1 rounded-full border border-success/30 bg-success/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.16em] text-success">
              <Check className="h-3 w-3" /> Tamamlandı
            </span>
          )}
        </div>
        {error && (
          <p className="text-sm text-destructive" role="alert">
            {error.message}
          </p>
        )}
        {!isValid && refs.length > 0 && (
          <p className="text-xs text-muted-foreground">
            Her referans için <strong>Metinden Alıntı</strong> ve en az bir tane{' '}
            <strong>Kanun No</strong> veya <strong>Kanun Adı</strong> doldurulmalı.
          </p>
        )}
        <div className="flex items-center justify-end gap-2">
          <Button type="button" variant="outline" onClick={onSkip} disabled={!canEdit || isSaving}>
            Atla
          </Button>
          <Button type="button" onClick={onSave} disabled={!canEdit || isSaving || !isValid}>
            {isSaving ? 'Kaydediliyor…' : 'Sakla'}
          </Button>
          {hasAnnotation && (
            <Button
              type="button"
              variant={isCompleted ? 'outline' : 'default'}
              onClick={onComplete}
              disabled={completeDisabled}
              className={cn(
                !isCompleted &&
                  'bg-success text-success-foreground shadow-sm hover:bg-success/90 focus-visible:ring-success',
              )}
            >
              {isCompleted ? (
                <Undo2 className="mr-1 h-4 w-4" />
              ) : (
                <Check className="mr-1 h-4 w-4" />
              )}
              {completeLabel}
            </Button>
          )}
        </div>
      </footer>
    </div>
  )
}
