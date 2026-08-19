import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { client, unwrap, unwrapVoid } from '@/api/client'
import type { components } from '@/api/types'
import { feedKeys } from '@/api/queries/feed'
import { draftKeys } from '@/api/queries/drafts'

export const annotationKeys = {
  all: ['annotations'] as const,
  byDoc: (id: string) => ['annotations', id] as const,
}

export function useAnnotationQuery(docId: string | null) {
  return useQuery({
    queryKey: annotationKeys.byDoc(docId ?? ''),
    queryFn: async ({ signal }) => {
      const r = await client.GET('/api/documents/{document_id}/annotation', {
        params: { path: { document_id: docId! } },
        signal,
      })
      return unwrap(r)
    },
    enabled: !!docId,
    staleTime: 30_000,
  })
}

interface SaveBody {
  document_id: string
  references: components['schemas']['ReferenceItem'][]
}

export function useSaveAnnotationMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: SaveBody) => unwrap(await client.POST('/api/annotations', { body })),
    onSuccess: (_data, body) => {
      void qc.invalidateQueries({ queryKey: annotationKeys.byDoc(body.document_id) })
    },
  })
}

export function useSkipAnnotationMutation() {
  return useMutation({
    mutationFn: async (docId: string) =>
      unwrapVoid(
        await client.POST('/api/annotations/{document_id}/skip', {
          params: { path: { document_id: docId } },
        }),
      ),
  })
}

interface CompleteBody {
  document_id: string
  completed: boolean
  // Phase 2 atomic save+complete: when set with completed=true, the
  // backend persists these refs AND flips the flag inside a single
  // BEGIN IMMEDIATE — eliminates the pre-Phase-3 save → complete →
  // delete_draft chain in handleComplete. Omit (or pass undefined)
  // to keep the legacy flag-flip-only contract. completed=false with
  // refs is rejected at the backend by CompleteRequest's validator
  // (422); callers must not send that combination.
  references?: components['schemas']['ReferenceItem'][]
  // Present only after the user saw a RED/YELLOW audit. The server recomputes
  // the bucket itself; this ack merely declares "I saw the comparison" and
  // carries the fingerprint so a prediction that changed meanwhile yields
  // 409 audit_stale instead of a silently different commit.
  audit_ack?: { prediction_fingerprint: string }
}

export function useCompleteAnnotationMutation() {
  const qc = useQueryClient()
  return useMutation({
    // `exactOptionalPropertyTypes` doesn't tolerate `references:
    // undefined` as a stand-in for "omit the key" — we conditionally
    // spread so the JSON body is `{ completed }` (legacy path) OR
    // `{ completed, references: [...] }` (atomic path), but never
    // `{ completed, references: undefined }`.
    mutationFn: async ({ document_id, completed, references, audit_ack }: CompleteBody) =>
      unwrapVoid(
        await client.POST('/api/annotations/{document_id}/complete', {
          params: { path: { document_id } },
          body: {
            completed,
            ...(references !== undefined && { references }),
            ...(audit_ack !== undefined && { audit_ack }),
          },
        }),
      ),
    onSuccess: (_data, { document_id }) => {
      void qc.invalidateQueries({ queryKey: annotationKeys.byDoc(document_id) })
      // Atomic complete writes through the drafts table too — drop the
      // cached draft snapshot so the next hydration reads fresh state
      // rather than echoing the stale pre-complete refs.
      void qc.invalidateQueries({ queryKey: draftKeys.byDoc(document_id) })
      // Toggle moves the document between review and verified tabs, so
      // both feed views must be refreshed regardless of which one the
      // caller is currently looking at.
      void qc.invalidateQueries({ queryKey: feedKeys.all })
    },
  })
}

export type PreAuditResult = components['schemas']['PreAuditResponse']
export type AuditDiscrepancy = components['schemas']['AuditDiscrepancy']

interface PreAuditBody {
  document_id: string
  references: components['schemas']['ReferenceItem'][]
}

/**
 * Read-only comparison against the cached G0 prediction. Writes nothing on the
 * server — the audit decision is recorded by /complete, inside its transaction.
 */
export function usePreAuditMutation() {
  return useMutation({
    mutationFn: async ({ document_id, references }: PreAuditBody) =>
      unwrap(
        await client.POST('/api/annotations/{document_id}/pre-audit', {
          params: { path: { document_id } },
          body: { references },
        }),
      ),
  })
}
