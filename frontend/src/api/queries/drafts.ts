import { useQuery } from '@tanstack/react-query'
import { client, unwrap } from '@/api/client'
import type { components } from '@/api/types'

interface DraftBody {
  references: components['schemas']['ReferenceItem'][]
}

export const draftKeys = {
  all: ['drafts'] as const,
  byDoc: (id: string) => ['drafts', id] as const,
}

export function useDraftQuery(docId: string | null) {
  return useQuery<DraftBody | null>({
    queryKey: draftKeys.byDoc(docId ?? ''),
    queryFn: async ({ signal }) => {
      const r = await client.GET('/api/drafts/{document_id}', {
        params: { path: { document_id: docId! } },
        signal,
      })
      if (r.response.status === 404) return null
      return (await unwrap(r)) as DraftBody
    },
    enabled: !!docId,
    retry: false,
    staleTime: Infinity,
  })
}

// PUT and DELETE intentionally not exposed here — useDraft (T5) owns them
// with AbortController + revision counter + isSaving gate.
