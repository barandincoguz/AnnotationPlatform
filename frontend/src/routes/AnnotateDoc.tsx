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
} from '@/hooks/useAnnotation'
import { useDraft } from '@/hooks/useDraft'
import { useReferencesState } from '@/hooks/useReferencesState'
import { useAnnotateStore } from '@/stores/annotateStore'
import { pickNextInFeedAcrossPages } from '@/lib/nextDocId'
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
    draftQueryStatus:
      draft.draftQuery.status === 'success'
        ? 'success'
        : draft.draftQuery.status === 'error'
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

  const canEdit = lock.status === 'held'

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
    })

    if (lockReleaseFailed) {
      toast.warning('Kilit serbest bırakılamadı; 90 saniye içinde otomatik temizlenir.')
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
          canEdit={canEdit}
          isSaving={saveMutation.isPending}
          error={errorForPanel}
          draftSaveStatus={draft.saveStatus}
        />
      </div>
    </div>
  )
}
