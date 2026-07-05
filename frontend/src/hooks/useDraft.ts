import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { client, ApiError } from '@/api/client'
import type { components } from '@/api/types'
import { useDraftQuery, draftKeys } from '@/api/queries/drafts'
import { feedKeys } from '@/api/queries/feed'

type ReferenceItem = components['schemas']['ReferenceItem']
type DraftSnapshot = { references: ReferenceItem[] } | null

export type DraftSaveStatus = 'idle' | 'saving' | 'saved' | 'error'

const DRAFT_DEBOUNCE_MS = 2_000

function debounce<T extends (...args: never[]) => unknown>(
  fn: T,
  ms: number,
): T & { cancel: () => void } {
  let timer: number | null = null
  const wrapped = ((...args: Parameters<T>) => {
    if (timer !== null) window.clearTimeout(timer)
    timer = window.setTimeout(() => {
      timer = null
      fn(...args)
    }, ms)
  }) as T & { cancel: () => void }
  wrapped.cancel = () => {
    if (timer !== null) {
      window.clearTimeout(timer)
      timer = null
    }
  }
  return wrapped
}

export function useDraft(docId: string) {
  const qc = useQueryClient()
  const draftQuery = useDraftQuery(docId)

  const [saveStatus, setSaveStatus] = useState<DraftSaveStatus>('idle')
  const inFlightAbortRef = useRef<AbortController | null>(null)
  const isBlockedRef = useRef(false)
  const revRef = useRef(0)

  // Invalidate the feed only when the draft transitions between
  // "empty / absent" and "has ≥1 ref" — that's the boundary that
  // moves a doc between Yeni and Kontrol Gerekiyor (Plan B semantics).
  // Per-keystroke autosaves that keep refs.length non-zero do NOT
  // touch the feed cache; otherwise an active DocList would refetch
  // ~ every 2 s while the user types.
  //
  // CRITICAL: this read must observe the pre-write cache state. The
  // caller is responsible for writing the post-state via
  // `qc.setQueryData(draftKeys.byDoc(docId), ...)` AFTER this call —
  // otherwise the next PUT/DELETE would compare against a stale prev
  // and miss/over-fire transitions (Codex review #3).
  const maybeInvalidateFeedAfterDraftWrite = useCallback(
    (newRefsLen: number) => {
      const prev = qc.getQueryData<DraftSnapshot>(draftKeys.byDoc(docId))
      const prevLen = prev?.references.length ?? 0
      const wasOnFeedReview = prevLen > 0
      const willBeOnFeedReview = newRefsLen > 0
      if (wasOnFeedReview !== willBeOnFeedReview) {
        void qc.invalidateQueries({ queryKey: feedKeys.all })
      }
    },
    [qc, docId],
  )

  const putRaw = useCallback(
    async (refs: ReferenceItem[], myRev: number) => {
      inFlightAbortRef.current?.abort()
      const ctrl = new AbortController()
      inFlightAbortRef.current = ctrl
      setSaveStatus('saving')
      try {
        const r = await client.PUT('/api/drafts/{document_id}', {
          params: { path: { document_id: docId } },
          body: { references: refs },
          signal: ctrl.signal,
        })
        if (myRev !== revRef.current) return
        if (r.error !== undefined) {
          setSaveStatus('error')
          return
        }
        setSaveStatus('saved')
        // Transition check must read the PRE-write cache, so it runs
        // before the setQueryData below. Codex review #3: without the
        // post-write cache update on PUT success, subsequent autosaves
        // kept seeing `prev=0` and would either over-invalidate per
        // keystroke OR miss the non-zero→empty boundary on a later
        // DELETE.
        maybeInvalidateFeedAfterDraftWrite(refs.length)
        qc.setQueryData(draftKeys.byDoc(docId), { references: refs })
      } catch (e) {
        if ((e as { name?: string })?.name === 'AbortError') return
        setSaveStatus('error')
      }
    },
    [docId, qc, maybeInvalidateFeedAfterDraftWrite],
  )

  // Autosave variant of DELETE: aborts a prior in-flight PUT/DELETE
  // and respects the revRef interlock so stale completions can't
  // overwrite saveStatus or shadow a fresh user edit. Kept separate
  // from `deleteMutation` below because the mutation API doesn't
  // play well with the abort + rev pattern.
  const deleteRaw = useCallback(
    async (myRev: number) => {
      inFlightAbortRef.current?.abort()
      const ctrl = new AbortController()
      inFlightAbortRef.current = ctrl
      setSaveStatus('saving')
      // Capture pre-state BEFORE the optimistic cache wipe below —
      // otherwise the transition check always reads "was empty" and
      // skips the invalidation that pulls the doc out of Kontrol Gerekiyor.
      const prev = qc.getQueryData<DraftSnapshot>(draftKeys.byDoc(docId))
      const hadRefs = (prev?.references.length ?? 0) > 0
      try {
        const r = await client.DELETE('/api/drafts/{document_id}', {
          params: { path: { document_id: docId } },
          signal: ctrl.signal,
        })
        if (myRev !== revRef.current) return
        if (r.error !== undefined && r.response.status !== 404) {
          setSaveStatus('error')
          return
        }
        setSaveStatus('saved')
        qc.setQueryData(draftKeys.byDoc(docId), null)
        if (hadRefs) {
          void qc.invalidateQueries({ queryKey: feedKeys.all })
        }
      } catch (e) {
        if ((e as { name?: string })?.name === 'AbortError') return
        setSaveStatus('error')
      }
    },
    [docId, qc],
  )

  const debouncedSave = useMemo(
    () =>
      debounce((refs: ReferenceItem[]) => {
        if (isBlockedRef.current) return
        const myRev = ++revRef.current
        if (refs.length === 0) {
          // Autosave with empty refs is the "I cleared everything"
          // signal. Pre-Phase-3 we PUT an empty `[]` row which left
          // a draft behind that shadowed the shared annotation in
          // some tab queries. DELETE is the cleaner intent: no row
          // = no draft = doc moves back to Yeni cleanly. The manual
          // "Kontrole Gönder" button takes a different path (POST /annotations).
          void deleteRaw(myRev)
        } else {
          void putRaw(refs, myRev)
        }
      }, DRAFT_DEBOUNCE_MS),
    [putRaw, deleteRaw],
  )

  // Cancel the captured-closure setTimeout when the memo regenerates
  // (docId change) or the component unmounts. Without this, a pending
  // 2-second edit from doc A whose timer is still ticking can resolve
  // and PUT against the OLD docId after the user has already navigated
  // to doc B (the closure captures the previous `putRaw`, which itself
  // is keyed off the old docId). Tracked as the root of the
  // "stale draft shadows shared annotation" symptom.
  useEffect(() => {
    return () => {
      debouncedSave.cancel()
      inFlightAbortRef.current?.abort()
    }
  }, [debouncedSave])

  const blockSavesUntilFurtherNotice = useCallback(() => {
    isBlockedRef.current = true
    debouncedSave.cancel()
    inFlightAbortRef.current?.abort()
  }, [debouncedSave])

  const unblockSaves = useCallback(() => {
    isBlockedRef.current = false
  }, [])

  // Explicit-callsite DELETE used by handleSave / handleSkip — uses
  // the mutation API so callers can await and surface failure
  // toasts. Invalidates the feed defensively; callers also invalidate
  // afterwards, the duplication is harmless because TanStack Query
  // coalesces invalidations within a microtask.
  const deleteMutation = useMutation({
    mutationFn: async () => {
      const prev = qc.getQueryData<DraftSnapshot>(draftKeys.byDoc(docId))
      const hadRefs = (prev?.references.length ?? 0) > 0
      const r = await client.DELETE('/api/drafts/{document_id}', {
        params: { path: { document_id: docId } },
      })
      if (r.error !== undefined && r.response.status !== 404) {
        const detail = (r.error as { detail?: unknown }).detail ?? r.error
        throw new ApiError(
          r.response.status,
          String(r.response.status),
          'Taslak silinemedi',
          detail,
        )
      }
      qc.setQueryData(draftKeys.byDoc(docId), null)
      if (hadRefs) {
        void qc.invalidateQueries({ queryKey: feedKeys.all })
      }
    },
  })

  return {
    draftQuery,
    debouncedSave,
    deleteMutation,
    saveStatus,
    blockSavesUntilFurtherNotice,
    unblockSaves,
  }
}
