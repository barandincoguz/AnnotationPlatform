import { useQuery } from '@tanstack/react-query'
import { client, unwrap } from '@/api/client'

export const docKeys = {
  all: ['documents'] as const,
  byId: (id: string) => ['documents', id] as const,
}

export function useDocQuery(docId: string | null) {
  return useQuery({
    queryKey: docKeys.byId(docId ?? ''),
    queryFn: async ({ signal }) =>
      unwrap(
        await client.GET('/api/documents/{document_id}', {
          params: { path: { document_id: docId! } },
          signal,
        }),
      ),
    enabled: !!docId,
    staleTime: 5 * 60_000,
  })
}
