import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { client, unwrap, unwrapVoid } from '@/api/client'
import type { components } from '@/api/types'

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
