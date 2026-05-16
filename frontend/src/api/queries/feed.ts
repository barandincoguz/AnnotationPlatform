import { useInfiniteQuery } from '@tanstack/react-query'
import { client, unwrap } from '@/api/client'
import type { SortKey, SortOrder } from '@/stores/annotateStore'

const PAGE_SIZE = 50

export type FeedTab = 'new' | 'review' | 'verified'

export interface FeedSort {
  by: SortKey
  order: SortOrder
}

/**
 * Query keys include the active sort so switching sort modes triggers
 * a fresh fetch (and so cached pages from one ordering are never
 * served under another).
 *
 * `tab(tab)` is preserved as a parent key prefix for invalidation
 * — `qc.invalidateQueries({ queryKey: feedKeys.tab(tab) })` wipes
 * every sort variant of that tab in one call.
 */
export const feedKeys = {
  all: ['feed'] as const,
  tab: (tab: FeedTab) => ['feed', tab] as const,
  tabSorted: (tab: FeedTab, sort: FeedSort) =>
    ['feed', tab, sort.by, sort.order] as const,
}

export function useFeedInfinite(tab: FeedTab, sort: FeedSort) {
  return useInfiniteQuery({
    queryKey: feedKeys.tabSorted(tab, sort),
    queryFn: async ({ pageParam, signal }) =>
      unwrap(
        await client.GET('/api/feed', {
          params: {
            query: {
              tab,
              limit: PAGE_SIZE,
              offset: pageParam,
              sort: sort.by,
              order: sort.order,
            },
          },
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
