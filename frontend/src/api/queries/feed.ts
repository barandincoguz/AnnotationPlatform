import { useInfiniteQuery } from '@tanstack/react-query'
import { client, unwrap } from '@/api/client'

const PAGE_SIZE = 50

export type FeedTab = 'new' | 'review' | 'verified'

export const feedKeys = {
  all: ['feed'] as const,
  tab: (tab: FeedTab) => ['feed', tab] as const,
}

export function useFeedInfinite(tab: FeedTab) {
  return useInfiniteQuery({
    queryKey: feedKeys.tab(tab),
    queryFn: async ({ pageParam, signal }) =>
      unwrap(
        await client.GET('/api/feed', {
          params: { query: { tab, limit: PAGE_SIZE, offset: pageParam } },
          signal,
        }),
      ),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.flatMap((p) => p.items).length
      return loaded < lastPage.total ? loaded : undefined
    },
    staleTime: 30_000,
  })
}
