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
    getNextPageParam: (_lastPage, allPages) => {
      // The backend now only computes `total` on page 0 (it's the most
      // expensive scan in shuffle/service.py, see polish-phase fix P3),
      // so we lock onto allPages[0].total as the authoritative count
      // and consult it on every page transition. Tolerates either
      // `null` (post-fix server) or a number (legacy / first-page).
      const loaded = allPages.flatMap((p) => p.items).length
      const total = allPages[0]?.total
      if (typeof total !== 'number') return undefined
      return loaded < total ? loaded : undefined
    },
    staleTime: 30_000,
  })
}
