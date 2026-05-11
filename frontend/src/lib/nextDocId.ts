import type { QueryClient } from '@tanstack/react-query'
import { feedKeys, type FeedTab } from '@/api/queries/feed'

export type NextDocResult = { type: 'next'; id: string } | { type: 'done' } | { type: 'empty' }

interface Page {
  items: { document_id: string }[]
  total: number
}
interface InfiniteData {
  pages: Page[]
  pageParams: unknown[]
}

export async function pickNextInFeedAcrossPages(opts: {
  qc: QueryClient
  currentTab: FeedTab
  currentDocId: string | null
}): Promise<NextDocResult> {
  const initial = opts.qc.getQueryData<InfiniteData>(feedKeys.tab(opts.currentTab))
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

  // At end of loaded pages — refetch and recurse once.
  if (items.length < total) {
    await opts.qc.refetchQueries({ queryKey: feedKeys.tab(opts.currentTab) })
    const after = opts.qc.getQueryData<InfiniteData>(feedKeys.tab(opts.currentTab))
    const grown = after ? itemsOf(after) : []
    if (grown.length > items.length) {
      return pickNextInFeedAcrossPages({
        qc: opts.qc,
        currentTab: opts.currentTab,
        currentDocId: opts.currentDocId,
      })
    }
  }

  return { type: 'done' }
}
