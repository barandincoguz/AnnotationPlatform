import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { client, ApiError } from '@/api/client'
import type { components } from '@/api/types'
import { useDraftQuery, draftKeys } from '@/api/queries/drafts'

type ReferenceItem = components['schemas']['ReferenceItem']

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
      } catch (e) {
        if ((e as { name?: string })?.name === 'AbortError') return
        setSaveStatus('error')
      }
    },
    [docId],
  )

  const debouncedSave = useMemo(
    () =>
      debounce((refs: ReferenceItem[]) => {
        if (isBlockedRef.current) return
        const myRev = ++revRef.current
        void putRaw(refs, myRev)
      }, DRAFT_DEBOUNCE_MS),
    [putRaw],
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

  const deleteMutation = useMutation({
    mutationFn: async () => {
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
