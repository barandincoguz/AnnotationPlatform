import { useCallback, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { AlertCircle, Loader2, RefreshCw } from 'lucide-react'
import { DocViewer } from '@/components/annotation/DocViewer'
import { ReferencePanel } from '@/components/annotation/ReferencePanel'
import { LockConflictModal } from '@/components/modals/LockConflictModal'
import { Button } from '@/components/ui/button'
import { useLock } from '@/hooks/useLock'
import { useDoc } from '@/hooks/useDoc'
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
import { areAllReferencesValid, checkAndRemoveDuplicateReferences } from '@/lib/validateReferences'
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
  const docQuery = useDoc(docId)

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

  const canEdit = lock.status === 'held' && refs.hydrated
  const isValid = areAllReferencesValid(refs.list)
  const hasAnnotation = !!annotation.data?.annotation
  const isCompleted = annotation.data?.annotation?.is_completed ?? false

  const handleSave = async () => {
    const { list: cleanedRefs, hasDuplicates } = checkAndRemoveDuplicateReferences(refs.list)
    if (hasDuplicates) {
      toast.warning('Yinelenen anotasyon silindi.')
      refs.updateAll(cleanedRefs)
    }
    draft.blockSavesUntilFurtherNotice()
    try {
      await saveMutation.mutateAsync({
        document_id: docId,
        references: cleanedRefs,
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
    const targetCompleted = !isCompleted
    const { list: cleanedRefs, hasDuplicates } = checkAndRemoveDuplicateReferences(refs.list)
    if (targetCompleted && hasDuplicates) {
      toast.warning('Yinelenen anotasyon silindi.')
      refs.updateAll(cleanedRefs)
    }
    draft.blockSavesUntilFurtherNotice()

    // Phase 3: single atomic POST.
    //
    // Pre-Phase-2 the frontend ran a 3-call chain (save → complete →
    // delete_draft) so that the on-screen refs were persisted before
    // the flag flipped. Backend Phase 2 collapsed all three into one
    // BEGIN IMMEDIATE on /complete: when `references` accompanies a
    // `completed=true` body the server saves the refs, flips the flag,
    // and deletes the caller's draft in a single transaction. The
    // pre-Phase-2 race (where blockSaves cancelled a pending PUT and
    // a stale `annotations.references_json` got frozen as "complete")
    // is now impossible — the server is the only writer of the final
    // state.
    //
    // Uncomplete (`completed=false`) is unchanged semantically: no refs
    // in the body, server flips the flag only. CompleteRequest's
    // model_validator rejects `completed=false` + refs at 422.
    try {
      await completeMutation.mutateAsync({
        document_id: docId,
        completed: targetCompleted,
        // Conditional spread — `exactOptionalPropertyTypes` rejects
        // `references: undefined` as an in-band signal. Only include
        // the key on the atomic path.
        ...(targetCompleted && { references: cleanedRefs }),
      })
    } catch {
      draft.unblockSaves()
      return
    }

    let lockReleaseFailed = false
    try {
      await lock.release()
    } catch {
      lockReleaseFailed = true
    }

    // Mutation onSuccess already invalidates feedKeys.all + the
    // doc's annotation + draft caches. We still refetch the active
    // tab explicitly so pickNextInFeedAcrossPages reads up-to-date
    // pages before navigating.
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
        <div className="max-w-md space-y-4 text-center">
          <AlertCircle aria-hidden="true" className="mx-auto h-8 w-8 text-destructive" />
          <div className="space-y-2">
            <h2 className="text-lg font-semibold">Düzenleme kilidi kaybedildi</h2>
            <p className="text-sm leading-relaxed text-muted-foreground">
              Bağlantı kesilmesi nedeniyle bu doküman üzerindeki düzenleme yetkiniz sonlandı.
              Çalışmalarınızı kaybetmemek için yeniden kilit almayı deneyebilirsiniz.
            </p>
          </div>
          <div className="flex items-center justify-center gap-2">
            <Button type="button" variant="outline" onClick={() => navigate('/', { replace: true })}>
              Listeye dön
            </Button>
            <Button type="button" onClick={lock.retry}>
              <RefreshCw aria-hidden="true" className="mr-2 h-4 w-4" />
              Yeniden kilitle
            </Button>
          </div>
        </div>
      </div>
    )
  }

  if (lock.status === 'error') {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="max-w-md space-y-4 text-center">
          <AlertCircle aria-hidden="true" className="mx-auto h-8 w-8 text-destructive" />
          <div className="space-y-2">
            <h2 className="text-lg font-semibold">Düzenleme kilidi alınamadı</h2>
            <p className="text-sm leading-relaxed text-muted-foreground">
              Bağlantıyı kontrol edip yeniden deneyin. Dokümanda yaptığınız kayıtlı çalışmalar
              etkilenmedi.
            </p>
          </div>
          <div className="flex items-center justify-center gap-2">
            <Button type="button" variant="outline" onClick={() => navigate('/', { replace: true })}>
              Listeye dön
            </Button>
            <Button type="button" onClick={lock.retry}>
              <RefreshCw aria-hidden="true" />
              Yeniden dene
            </Button>
          </div>
        </div>
      </div>
    )
  }

  if (lock.status === 'idle' || lock.status === 'acquiring') {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
          Düzenleme kilidi alınıyor...
        </div>
      </div>
    )
  }

  if (!refs.hydrated) {
    const draftRefs = draft.draftQuery.data?.references
    const hasDraftRefs = Array.isArray(draftRefs) && draftRefs.length > 0
    const referenceLoadFailed =
      draft.draftQuery.status === 'error'
      || (
        draft.draftQuery.status === 'success'
        && !hasDraftRefs
        && annotation.status === 'error'
      )

    return (
      <div className="grid h-full grid-cols-[60%_40%] overflow-hidden">
        <div className="border-r border-border overflow-hidden">
          <DocViewer docId={docId} />
        </div>
        <div className="flex items-center justify-center p-8">
          {referenceLoadFailed ? (
            <div className="max-w-sm space-y-4 text-center">
              <AlertCircle
                aria-hidden="true"
                className="mx-auto h-8 w-8 text-destructive"
              />
              <div className="space-y-2">
                <h2 className="text-lg font-semibold">Referanslar yüklenemedi</h2>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  Kayıtlı referanslar doğrulanmadan düzenleme açılamaz.
                  Bağlantıyı kontrol edip yeniden deneyin.
                </p>
              </div>
              <Button
                type="button"
                onClick={() => {
                  void Promise.all([
                    draft.draftQuery.refetch(),
                    annotation.refetch(),
                  ])
                }}
              >
                <RefreshCw aria-hidden="true" />
                Yeniden dene
              </Button>
            </div>
          ) : (
            <div
              className="flex items-center gap-2 text-sm font-medium text-muted-foreground"
              role="status"
            >
              <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
              Referanslar yükleniyor...
            </div>
          )}
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
          docText={docQuery.data?.pdf_text ?? ''}
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
