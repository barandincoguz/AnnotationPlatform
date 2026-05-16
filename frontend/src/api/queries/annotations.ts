import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { client, unwrap, unwrapVoid } from '@/api/client'
import type { components } from '@/api/types'
import { feedKeys } from '@/api/queries/feed'

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
}

export function useCompleteAnnotationMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ document_id, completed }: CompleteBody) =>
      unwrapVoid(
        await client.POST('/api/annotations/{document_id}/complete', {
          params: { path: { document_id } },
          body: { completed },
        }),
      ),
    onSuccess: (_data, { document_id }) => {
      void qc.invalidateQueries({ queryKey: annotationKeys.byDoc(document_id) })
      // Toggle moves the document between review and verified tabs, so
      // both feed views must be refreshed regardless of which one the
      // caller is currently looking at.
      void qc.invalidateQueries({ queryKey: feedKeys.all })
    },
  })
}
