import { useCallback, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { DocViewer } from '@/components/annotation/DocViewer'
import { ReferencePanel } from '@/components/annotation/ReferencePanel'
import { LockConflictModal } from '@/components/modals/LockConflictModal'
import { useLock } from '@/hooks/useLock'
import {
  useAnnotation,
  useSaveAnnotationMutation,
  useSkipAnnotationMutation,
  useCompleteAnnotationMutation,
} from '@/hooks/useAnnotation'
import { useDraft } from '@/hooks/useDraft'
import { useReferencesState } from '@/hooks/useReferencesState'
import { useAnnotateStore } from '@/stores/annotateStore'
import { pickNextInFeedAcrossPages } from '@/lib/nextDocId'
import { areAllReferencesValid } from '@/lib/validateReferences'
import { ApiError } from '@/api/client'
import { feedKeys } from '@/api/queries/feed'
import type { components } from '@/api/types'

type ReferenceItem = components['schemas']['ReferenceItem']

export function AnnotateDoc() {
  const params = useParams<{ docId: string }>()
  const docId = params.docId

  if (!docId) {
    return <div className="p-4 text-sm text-muted-foreground">Doküman ID yok.</div>
  }

  return <AnnotateDocInner docId={docId} />
}

function AnnotateDocInner({ docId }: { docId: string }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const currentTab = useAnnotateStore((s) => s.currentTab)
  // Cached feed pages live under the full (tab, sort, order) query
  // key now, so we have to pass the active sort to pickNextInFeed for
  // the lookup to hit the same data DocList is showing.
  const currentSort = useAnnotateStore((s) => s.sort[s.currentTab])
  const [modalOpen, setModalOpen] = useState(true)

  const lock = useLock(docId)
  const annotation = useAnnotation(docId)
  const draft = useDraft(docId)

  const onChangeRefs = useCallback(
    (next: ReferenceItem[]) => {
      draft.debouncedSave(next)
    },
    [draft],
  )

  const refs = useReferencesState({
    sourceKey: docId,
    draftQueryStatus:
      draft.draftQuery.status === 'success'
        ? 'success'
        : draft.draftQuery.status === 'error'
          ? 'error'
          : 'pending',
    // Race fix: when draft resolves as null/empty first, hydration
    // MUST wait for annotation status before committing — otherwise
    // `annotationData=null` gets locked in as the initial ref list
    // and the late-arriving annotation refs never reach the UI.
    annotationQueryStatus:
      annotation.status === 'success'
        ? 'success'
        : annotation.status === 'error'
          ? 'error'
          : 'pending',
    draftData: draft.draftQuery.data ?? null,
    annotationData: annotation.data?.annotation
      ? { references: annotation.data.annotation.references }
      : null,
    onChange: onChangeRefs,
  })

  const saveMutation = useSaveAnnotationMutation()
  const skipMutation = useSkipAnnotationMutation()
  const completeMutation = useCompleteAnnotationMutation()

  const canEdit = lock.status === 'held'
  const isValid = areAllReferencesValid(refs.list)
  const hasAnnotation = !!annotation.data?.annotation
  const isCompleted = annotation.data?.annotation?.is_completed ?? false

  const handleSave = async () => {
    draft.blockSavesUntilFurtherNotice()
    try {
      await saveMutation.mutateAsync({
        document_id: docId,
        references: refs.list,
      })
    } catch {
      draft.unblockSaves()
      return
    }

    let lockReleaseFailed = false
    let draftDeleteFailed = false
    try {
      await draft.deleteMutation.mutateAsync()
    } catch {
      draftDeleteFailed = true
    }
    try {
      await lock.release()
    } catch {
      lockReleaseFailed = true
    }

    await qc.invalidateQueries({ queryKey: feedKeys.all })
    await qc.refetchQueries({ queryKey: feedKeys.tab(currentTab) })

    const next = await pickNextInFeedAcrossPages({
      qc,
      currentTab,
      currentDocId: docId,
      sort: currentSort,
    })

    if (lockReleaseFailed) {
      toast.warning('Kilit serbest bırakılamadı; 5 dakika içinde otomatik temizlenir.')
    }
    if (draftDeleteFailed) {
      toast.warning('Taslak silinemedi; bir sonraki düzenlemede üzerine yazılacak.')
    }

    if (next.type === 'next') {
      navigate(`/docs/${next.id}`, { replace: true })
    } else if (next.type === 'done') {
      toast.success('Bu sekmedeki tüm dokümanlar bitti.')
      navigate('/', { replace: true })
    } else {
      navigate('/', { replace: true })
    }
  }

  const handleComplete = async () => {
    if (!hasAnnotation) return
    const targetCompleted = !isCompleted
    draft.blockSavesUntilFurtherNotice()

    // CRITICAL: when completing, persist whatever the user has on screen
    // BEFORE flipping the is_completed flag. The backend `set_complete`
    // endpoint only flips the flag — it reads `references_json` from the
    // existing annotation row and writes a `complete_mark` version row;
    // it never consults the drafts table. Without this pre-save:
    //   - the user types refs into the UI
    //   - the 2s draft-debounce hasn't fired yet (or the latest tick is
    //     still in flight)
    //   - the user clicks "Tamamla"
    //   - blockSavesUntilFurtherNotice() cancels the pending PUT
    //   - the document gets marked complete with whatever was previously
    //     committed to `annotations.references_json` (often empty / stale
    //     / a different user's work)
    //   - the on-screen content the user "completed" is silently dropped
    //     into the orphan drafts row (Bug: completed annotations of "a"
    //     with 11-ref drafts left over)
    // Uncomplete (targetCompleted=false) skips this — the user is
    // reversing a prior commit, not freezing a new one.
    if (targetCompleted) {
      try {
        await saveMutation.mutateAsync({
          document_id: docId,
          references: refs.list,
        })
      } catch {
        draft.unblockSaves()
        return
      }
    }

    try {
      await completeMutation.mutateAsync({
        document_id: docId,
        completed: targetCompleted,
      })
    } catch {
      draft.unblockSaves()
      return
    }

    // Drop the now-stale draft row so a later viewer (or the same user
    // uncomplete-then-recomplete) doesn't see ghost content from the
    // pre-save period.
    let draftDeleteFailed = false
    if (targetCompleted) {
      try {
        await draft.deleteMutation.mutateAsync()
      } catch {
        draftDeleteFailed = true
      }
    }

    let lockReleaseFailed = false
    try {
      await lock.release()
    } catch {
      lockReleaseFailed = true
    }

    await qc.invalidateQueries({ queryKey: feedKeys.all })
    await qc.refetchQueries({ queryKey: feedKeys.tab(currentTab) })

    const next = await pickNextInFeedAcrossPages({
      qc,
      currentTab,
      currentDocId: docId,
      sort: currentSort,
    })

    if (lockReleaseFailed) {
      toast.warning('Kilit serbest bırakılamadı; 5 dakika içinde otomatik temizlenir.')
    }
    if (draftDeleteFailed) {
      toast.warning('Taslak silinemedi; bir sonraki düzenlemede üzerine yazılacak.')
    }
    toast.success(
      targetCompleted
        ? 'Doküman tamamlandı olarak işaretlendi.'
        : 'Tamamlanma işareti geri alındı.',
    )

    if (next.type === 'next') {
      navigate(`/docs/${next.id}`, { replace: true })
    } else if (next.type === 'done') {
      navigate('/', { replace: true })
    } else {
      navigate('/', { replace: true })
    }
  }

  const handleSkip = async () => {
    try {
      await skipMutation.mutateAsync(docId)
    } catch {
      /* best-effort */
    }
    try {
      await draft.deleteMutation.mutateAsync()
    } catch {
      /* best-effort */
    }
    await qc.invalidateQueries({ queryKey: feedKeys.all })
    const next = await pickNextInFeedAcrossPages({
      qc,
      currentTab,
      currentDocId: docId,
      sort: currentSort,
    })
    if (next.type === 'next') {
      navigate(`/docs/${next.id}`, { replace: true })
    } else {
      navigate('/', { replace: true })
    }
  }

  if (lock.status === 'conflict') {
    return (
      <LockConflictModal
        open={modalOpen}
        conflictUsername={lock.conflictUsername}
        isSameUser={lock.conflictIsSameUser}
        onClose={() => {
          setModalOpen(false)
          navigate('/', { replace: true })
        }}
      />
    )
  }

  if (lock.status === 'lost') {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="space-y-3 text-center">
          <p className="text-lg font-medium">Kilit kaybedildi</p>
          <p className="text-sm text-muted-foreground">
            Bu doküman üzerindeki düzenleme yetkiniz sonlandı.
          </p>
          <button
            type="button"
            className="text-sm underline"
            onClick={() => navigate('/', { replace: true })}
          >
            Listeye dön
          </button>
        </div>
      </div>
    )
  }

  const errorForPanel = saveMutation.error instanceof ApiError ? saveMutation.error : null

  return (
    <div className="grid h-full grid-cols-[60%_40%] overflow-hidden">
      <div className="border-r border-border overflow-hidden">
        <DocViewer docId={docId} />
      </div>
      <div className="overflow-hidden">
        <ReferencePanel
          refs={refs.list}
          onAdd={refs.add}
          onUpdate={refs.update}
          onRemove={refs.remove}
          onSave={() => {
            void handleSave()
          }}
          onSkip={() => {
            void handleSkip()
          }}
          onComplete={() => {
            void handleComplete()
          }}
          canEdit={canEdit}
          isSaving={saveMutation.isPending}
          isCompleting={completeMutation.isPending}
          error={errorForPanel}
          draftSaveStatus={draft.saveStatus}
          isValid={isValid}
          hasAnnotation={hasAnnotation}
          isCompleted={isCompleted}
        />
      </div>
    </div>
  )
}
