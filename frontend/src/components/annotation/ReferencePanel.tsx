import { Plus, Loader2, Check, AlertCircle, Undo2, BookMarked } from 'lucide-react'
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
      <span className="inline-flex items-center gap-1.5 text-[12px] font-medium text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Taslak kaydediliyor…
      </span>
    )
  }
  if (status === 'saved') {
    return (
      <span className="inline-flex items-center gap-1.5 text-[12px] font-medium text-success">
        <Check className="h-3.5 w-3.5" /> Taslak kaydedildi
      </span>
    )
  }
  if (status === 'error') {
    return (
      <span className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-destructive">
        <AlertCircle className="h-3.5 w-3.5" /> Taslak hatası
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
      {/* Editorial panel header — gives the right column a real frame
          instead of starting cold on the first reference card. */}
      <header className="flex items-center justify-between gap-2 border-b border-border/60 bg-card/60 px-5 py-3">
        <div className="flex items-center gap-2.5">
          <BookMarked aria-hidden="true" className="h-4 w-4 text-accent" />
          <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
            Referanslar
          </span>
          <span className="font-mono text-[13px] font-bold tabular-nums text-foreground">
            {refs.length}
          </span>
        </div>
        {hasAnnotation && isCompleted && (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-success/30 bg-success/10 px-2.5 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-success">
            <Check className="h-3.5 w-3.5" /> Tamamlandı
          </span>
        )}
      </header>
      <div className="flex-1 space-y-4 overflow-auto p-5">
        {refs.length === 0 ? (
          <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border/70 bg-card/40 px-6 py-10 text-center">
            <span aria-hidden className="font-display text-5xl leading-none text-accent/30">
              §
            </span>
            <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              Henüz referans yok
            </p>
            <p className="text-[15px] leading-relaxed text-muted-foreground/90">
              &ldquo;+ Yeni Referans&rdquo; ile başlayın; eklediğiniz her atıf bir kart olarak görünür.
            </p>
          </div>
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
          className="w-full border-dashed border-accent2/40 text-accent2 hover:bg-accent2/5 hover:text-accent2 hover:border-accent2"
        >
          <Plus /> Yeni Referans
        </Button>
      </div>
      <Separator />
      <footer className="space-y-3 bg-card/60 p-5">
        <div className="flex items-center justify-between">
          <DraftStatusBadge status={draftSaveStatus} />
        </div>
        {error && (
          <p
            className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-[14px] font-medium text-destructive"
            role="alert"
          >
            {error.message}
          </p>
        )}
        {!isValid && refs.length > 0 && (
          <p className="rounded-md bg-warning/10 px-3 py-2 text-[13px] leading-relaxed text-foreground/80 border border-warning/25">
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
          {/* The Phase 2 backend now supports first-time atomic
              complete (no prior annotation row required), so the
              button visibility no longer gates on hasAnnotation —
              completeDisabled (canEdit + isValid + !isSaving) is
              the real safety net. The Undo / "Geri Al" path also
              shows here, but is reachable only when isCompleted=true
              (which implies hasAnnotation=true anyway). */}
          <Button
            type="button"
            variant={isCompleted ? 'outline' : 'success'}
            onClick={onComplete}
            disabled={completeDisabled}
          >
            {isCompleted ? <Undo2 /> : <Check />}
            {completeLabel}
          </Button>
        </div>
      </footer>
    </div>
  )
}
