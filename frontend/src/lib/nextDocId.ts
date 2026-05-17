import type { QueryClient } from '@tanstack/react-query'
import { feedKeys, type FeedSort, type FeedTab } from '@/api/queries/feed'

export type NextDocResult = { type: 'next'; id: string } | { type: 'done' } | { type: 'empty' }

interface Page {
  items: { document_id: string }[]
  total: number
}
interface InfiniteData {
  pages: Page[]
  pageParams: unknown[]
}

interface PickNextOpts {
  qc: QueryClient
  currentTab: FeedTab
  currentDocId: string | null
  /**
   * Optional active sort. When provided, looks up the cache under the
   * sorted query key so callers see exactly the ordering they were
   * navigating. When omitted, falls back to the legacy prefix-only
   * lookup (preserves existing tests that seed via `feedKeys.tab`).
   */
  sort?: FeedSort
  /**
   * Recursion depth guard. The intended contract is "at end of loaded
   * pages: refetch once and try again." Anything beyond one recursion
   * means the cache mutated in a way we don't expect (SSE-triggered
   * invalidation that keeps appending pages without ever including the
   * next index after idx). Bail to `done` rather than spinning.
   * Callers MUST NOT pass this — it's an internal recursion marker.
   */
  _depth?: number
}

const MAX_RECURSION_DEPTH = 1

export async function pickNextInFeedAcrossPages(opts: PickNextOpts): Promise<NextDocResult> {
  const queryKey = opts.sort
    ? feedKeys.tabSorted(opts.currentTab, opts.sort)
    : feedKeys.tab(opts.currentTab)

  const initial = opts.qc.getQueryData<InfiniteData>(queryKey)
  if (!initial) return { type: 'empty' }

  const itemsOf = (data: InfiniteData) => data.pages.flatMap((p) => p.items)
  const items = itemsOf(initial)
  if (items.length === 0) return { type: 'empty' }
  const total = initial.pages[0]?.total ?? items.length

  const idx = opts.currentDocId ? items.findIndex((d) => d.document_id === opts.currentDocId) : -1

  if (idx === -1) {
    return { type: 'next', id: items[0]!.document_id }
  }
  const direct = items[idx + 1]
  if (direct) return { type: 'next', id: direct.document_id }

  // At end of loaded pages — refetch and recurse once. The depth guard
  // is the load-bearing termination signal: if the cache mutates such
  // that `grown.length` keeps incrementing without ever including the
  // next index after `idx` (plausible under flaky network + SSE
  // invalidation racing with the refetch), the recursion would spin
  // forever otherwise.
  const depth = opts._depth ?? 0
  if (items.length < total && depth < MAX_RECURSION_DEPTH) {
    await opts.qc.refetchQueries({ queryKey })
    const after = opts.qc.getQueryData<InfiniteData>(queryKey)
    const grown = after ? itemsOf(after) : []
    if (grown.length > items.length) {
      const recurseOpts: PickNextOpts = {
        qc: opts.qc,
        currentTab: opts.currentTab,
        currentDocId: opts.currentDocId,
        _depth: depth + 1,
      }
      if (opts.sort) recurseOpts.sort = opts.sort
      return pickNextInFeedAcrossPages(recurseOpts)
    }
  }

  return { type: 'done' }
}
