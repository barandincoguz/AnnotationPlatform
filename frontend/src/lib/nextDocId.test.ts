import { describe, it, expect } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { pickNextInFeedAcrossPages } from './nextDocId'
import { feedKeys } from '@/api/queries/feed'

function seedFeed(
  qc: QueryClient,
  tab: 'new' | 'review' | 'verified',
  pages: { items: { document_id: string }[]; total: number }[],
) {
  qc.setQueryData(feedKeys.tab(tab), { pages, pageParams: pages.map((_, i) => i) })
}

describe('pickNextInFeedAcrossPages', () => {
  it('returns next id within a single page', async () => {
    const qc = new QueryClient()
    seedFeed(qc, 'new', [
      { items: [{ document_id: 'a' }, { document_id: 'b' }, { document_id: 'c' }], total: 3 },
    ])
    const result = await pickNextInFeedAcrossPages({ qc, currentTab: 'new', currentDocId: 'a' })
    expect(result).toEqual({ type: 'next', id: 'b' })
  })

  it('returns "done" when current is last and no more pages', async () => {
    const qc = new QueryClient()
    seedFeed(qc, 'new', [
      { items: [{ document_id: 'a' }, { document_id: 'b' }], total: 2 },
    ])
    const result = await pickNextInFeedAcrossPages({ qc, currentTab: 'new', currentDocId: 'b' })
    expect(result).toEqual({ type: 'done' })
  })

  it('returns "empty" when feed has no items', async () => {
    const qc = new QueryClient()
    seedFeed(qc, 'new', [{ items: [], total: 0 }])
    const result = await pickNextInFeedAcrossPages({ qc, currentTab: 'new', currentDocId: 'x' })
    expect(result).toEqual({ type: 'empty' })
  })

  it('returns first item when currentDocId is not in feed', async () => {
    const qc = new QueryClient()
    seedFeed(qc, 'new', [
      { items: [{ document_id: 'a' }, { document_id: 'b' }], total: 2 },
    ])
    const result = await pickNextInFeedAcrossPages({ qc, currentTab: 'new', currentDocId: 'zzz' })
    expect(result).toEqual({ type: 'next', id: 'a' })
  })

  it('returns "empty" when no query state exists', async () => {
    const qc = new QueryClient()
    const result = await pickNextInFeedAcrossPages({ qc, currentTab: 'new', currentDocId: null })
    expect(result).toEqual({ type: 'empty' })
  })
})
