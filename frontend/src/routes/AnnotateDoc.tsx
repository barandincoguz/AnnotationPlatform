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
import { QualityAuditPanel, discrepancyKey } from '@/components/annotation/QualityAuditPanel'
import { usePreAuditMutation } from '@/hooks/useAnnotation'
import type { AuditDiscrepancy, PreAuditResult } from '@/api/queries/annotations'
import type { QuoteTarget } from '@/lib/quoteMatcher'
import { useEffect, useMemo, useRef } from 'react'
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

  type AuditState =
    | { phase: 'idle' }
    | { phase: 'running' }
    | { phase: 'open'; result: PreAuditResult; staleNotice: string | null }

  const [audit, setAudit] = useState<AuditState>({ phase: 'idle' })
  const [acceptedKeys, setAcceptedKeys] = useState<ReadonlySet<string>>(new Set())
  const [activeHighlightId, setActiveHighlightId] = useState<string | null>(null)
  const [modelUnavailableReason, setModelUnavailableReason] = useState<string | null>(null)
  const preAuditMutation = usePreAuditMutation()
  // Mirror of the live reference list. `refs.list` lags by one render after a
  // reducer dispatch and the draft PUT is debounced, so a "Tamamla" click in
  // the same tick as an accepted suggestion must read from here.
  const refsRef = useRef<ReferenceItem[]>([])

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
  useEffect(() => {
    refsRef.current = refs.list
  }, [refs.list])

  const isValid = areAllReferencesValid(refs.list)
  const hasAnnotation = !!annotation.data?.annotation
  const isCompleted = annotation.data?.annotation?.is_completed ?? false

  const handleSave = async () => {
    const { list: cleanedRefs, hasDuplicates } = checkAndRemoveDuplicateReferences(refsRef.current)
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

  const runPreAudit = async (references: ReferenceItem[]) =>
    preAuditMutation.mutateAsync({ document_id: docId, references })

  const finalizeComplete = async (
    targetCompleted: boolean,
    cleanedRefs: ReferenceItem[],
    ack: { prediction_fingerprint: string } | undefined,
    attempt = 0,
  ) => {
    draft.blockSavesUntilFurtherNotice()
    try {
      await completeMutation.mutateAsync({
        document_id: docId,
        completed: targetCompleted,
        ...(targetCompleted && { references: cleanedRefs }),
        ...(ack !== undefined && { audit_ack: ack }),
      })
    } catch (err) {
      draft.unblockSaves()
      const code = err instanceof ApiError ? err.code : ''
      const auditConflict = code === 'audit_stale' || code === 'audit_required'
      if (!auditConflict || attempt >= 1) {
        setAudit({ phase: 'idle' })
        return
      }
      // The predict-agent pushed a fresher prediction while the user worked.
      // Re-audit quietly, then either reopen the panel with a soft notice or
      // commit once more with the fresh fingerprint. Never a scary error.
      try {
        const fresh = await runPreAudit(cleanedRefs)
        if (fresh.audit_status === 'ready' && fresh.bucket !== 'GREEN') {
          setAudit({
            phase: 'open',
            result: fresh,
            staleNotice:
              'Yeni model tahmini alındı, lütfen son kez teyit edip Tamamla\'ya basınız.',
          })
          return
        }
        await finalizeComplete(
          targetCompleted,
          cleanedRefs,
          fresh.prediction_fingerprint
            ? { prediction_fingerprint: fresh.prediction_fingerprint }
            : undefined,
          attempt + 1,
        )
      } catch {
        setAudit({ phase: 'idle' })
        toast.error('Model kontrolü yenilenemedi, lütfen tekrar deneyin.')
      }
      return
    }

    setAudit({ phase: 'idle' })

    let lockReleaseFailed = false
    try {
      await lock.release()
    } catch {
      lockReleaseFailed = true
    }

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
    } else {
      navigate('/', { replace: true })
    }
  }

  const handleComplete = async () => {
    console.log("handleComplete called!")
    const targetCompleted = !isCompleted
    const { list: cleanedRefs, hasDuplicates } = checkAndRemoveDuplicateReferences(
      refsRef.current,
    )
    if (targetCompleted && hasDuplicates) {
      toast.warning('Yinelenen anotasyon silindi.')
      refs.updateAll(cleanedRefs)
      refsRef.current = cleanedRefs
    }

    // Uncomplete reverses a prior commit; there is nothing to audit.
    if (!targetCompleted) {
      await finalizeComplete(false, cleanedRefs, undefined)
      return
    }

    setAudit({ phase: 'running' })
    let result: PreAuditResult
    try {
      result = await runPreAudit(cleanedRefs)
      console.log("PreAudit Result:", result)
    } catch (err) {
      console.log("PreAudit error:", err)
      // The audit is advisory infrastructure — it must never block a submit.
      setAudit({ phase: 'idle' })
      toast.warning('Model kontrolü çalıştırılamadı; kaydınız etkilenmedi.')
      await finalizeComplete(true, cleanedRefs, undefined)
      return
    }

    if (result.audit_status === 'model_unavailable') {
      console.log("Model unavailable")
      setModelUnavailableReason(result.reason ?? 'no_prediction')
      setAudit({ phase: 'idle' })
      await finalizeComplete(true, cleanedRefs, undefined)
      return
    }
    setModelUnavailableReason(null)
    const ack = result.prediction_fingerprint
      ? { prediction_fingerprint: result.prediction_fingerprint }
      : undefined
    if (result.bucket === 'GREEN') {
      console.log("GREEN bucket")
      setAudit({ phase: 'idle' })
      await finalizeComplete(true, cleanedRefs, ack)
      return
    }
    console.log("Setting phase to open", result.bucket)
    setAudit({ phase: 'open', result, staleNotice: null })
  }


  const handleCompare = async () => {
    setAudit({ phase: 'running' })
    try {
      const result = await runPreAudit(refsRef.current)
      if (result.audit_status === 'model_unavailable') {
        setModelUnavailableReason(result.reason ?? 'no_prediction')
        setAudit({ phase: 'idle' })
        return
      }
      setModelUnavailableReason(null)
      if (result.bucket === 'GREEN') {
        setAudit({ phase: 'idle' })
        toast.success('Model tahmini ile etiketleriniz uyuşuyor.')
        return
      }
      setAudit({ phase: 'open', result, staleNotice: null })
    } catch {
      setAudit({ phase: 'idle' })
      toast.warning('Model kontrolü çalıştırılamadı.')
    }
  }

  const handleAcceptSuggestion = (discrepancy: AuditDiscrepancy) => {
    const model = discrepancy.model_reference
    if (!model?.source_text) return
    const next: ReferenceItem[] = [
      ...refsRef.current,
      {
        kanun_no: model.kanun_no ?? null,
        kanun_ad: model.kanun_ad ?? null,
        madde: model.madde ?? null,
        fikra: model.fikra ?? null,
        bent: model.bent ?? null,
        source_text: model.source_text,
      },
    ]
    // Synchronous write closes the debounce race: a "Tamamla" click in this
    // same tick still commits the accepted suggestion.
    refsRef.current = next
    refs.updateAll(next)
    setAcceptedKeys((prev) => new Set(prev).add(discrepancyKey(discrepancy)))
    toast.success('Model önerisi listenize eklendi.')
  }

  const handleOverride = async () => {
    if (audit.phase !== 'open') return
    const ack = audit.result.prediction_fingerprint
      ? { prediction_fingerprint: audit.result.prediction_fingerprint }
      : undefined
    await finalizeComplete(true, refsRef.current, ack)
  }

  const highlights = useMemo<QuoteTarget[]>(() => {
    if (audit.phase !== 'open') return []
    return (audit.result.discrepancies ?? [])
      .filter((d) => d.model_reference?.source_text)
      .map((d) => ({
        id: discrepancyKey(d),
        quote: d.model_reference!.source_text!,
        ...(d.madde && { near: d.madde }),
      }))
  }, [audit])

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
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate('/', { replace: true })}
            >
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
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate('/', { replace: true })}
            >
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
      draft.draftQuery.status === 'error' ||
      (draft.draftQuery.status === 'success' && !hasDraftRefs && annotation.status === 'error')

    return (
      <div className="grid h-full grid-cols-[minmax(0,60%)_minmax(0,40%)] overflow-hidden">
        <div className="min-w-0 overflow-hidden border-r border-border">
          <DocViewer docId={docId} />
        </div>
        <div className="min-w-0 overflow-hidden">
          <div className="flex h-full items-center justify-center p-8">
            {referenceLoadFailed ? (
              <div className="max-w-sm space-y-4 text-center">
                <AlertCircle aria-hidden="true" className="mx-auto h-8 w-8 text-destructive" />
                <div className="space-y-2">
                  <h2 className="text-lg font-semibold">Referanslar yüklenemedi</h2>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    Kayıtlı referanslar doğrulanmadan düzenleme açılamaz. Bağlantıyı kontrol edip
                    yeniden deneyin.
                  </p>
                </div>
                <Button
                  type="button"
                  onClick={() => {
                    void Promise.all([draft.draftQuery.refetch(), annotation.refetch()])
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
      </div>
    )
  }

  const errorForPanel = saveMutation.error instanceof ApiError ? saveMutation.error : null

  return (
    <div className="grid h-full grid-cols-[minmax(0,60%)_minmax(0,40%)] overflow-hidden">
      <div className="min-w-0 overflow-hidden border-r border-border">
        <DocViewer docId={docId} highlights={highlights} activeHighlightId={activeHighlightId} />
      </div>
      <div className="min-w-0 overflow-hidden">
        {audit.phase === 'open' ? (
          <QualityAuditPanel
            result={audit.result}
            acceptedKeys={acceptedKeys}
            staleNotice={audit.staleNotice}
            isCompleting={completeMutation.isPending}
            onAccept={handleAcceptSuggestion}
            onHover={setActiveHighlightId}
            onComplete={() => {
              void handleComplete()
            }}
            onOverride={() => {
              void handleOverride()
            }}
            onBackToEdit={() => {
              setAudit({ phase: 'idle' })
              setActiveHighlightId(null)
            }}
          />
        ) : (
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
            onCompare={() => {
              void handleCompare()
            }}
            canEdit={canEdit}
            isSaving={saveMutation.isPending}
            isCompleting={completeMutation.isPending}
            isAuditing={audit.phase === 'running'}
            modelUnavailableReason={modelUnavailableReason}
            error={errorForPanel}
            draftSaveStatus={draft.saveStatus}
            isValid={isValid}
            hasAnnotation={hasAnnotation}
            isCompleted={isCompleted}
          />
        )}
      </div>
    </div>
  )
}
