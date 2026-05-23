import { describe, it, expect, beforeEach } from 'vitest'
import { useAnnotateStore, isSortAvailable } from './annotateStore'

beforeEach(() => {
  sessionStorage.clear()
  useAnnotateStore.setState({
    currentTab: 'new',
    sort: {
      new: { by: 'document_id', order: 'desc' },
      review: { by: 'document_id', order: 'desc' },
      verified: { by: 'document_id', order: 'desc' },
    },
  })
})

describe('annotateStore', () => {
  it('defaults to "new" tab', () => {
    expect(useAnnotateStore.getState().currentTab).toBe('new')
  })

  it('setCurrentTab updates and persists to sessionStorage', () => {
    useAnnotateStore.getState().setCurrentTab('review')
    expect(useAnnotateStore.getState().currentTab).toBe('review')
    expect(sessionStorage.getItem('annotate.store.v4')).toContain('review')
  })

  it('only accepts valid tabs', () => {
    useAnnotateStore.getState().setCurrentTab('verified')
    expect(useAnnotateStore.getState().currentTab).toBe('verified')
  })

  it('Phase 6: every tab defaults to document_id DESC', () => {
    const { sort } = useAnnotateStore.getState()
    expect(sort.new).toEqual({ by: 'document_id', order: 'desc' })
    expect(sort.review).toEqual({ by: 'document_id', order: 'desc' })
    expect(sort.verified).toEqual({ by: 'document_id', order: 'desc' })
  })

  it('setSort mutates a single tab without touching the others', () => {
    useAnnotateStore.getState().setSort('new', { by: 'konu', order: 'asc' })
    const { sort } = useAnnotateStore.getState()
    expect(sort.new).toEqual({ by: 'konu', order: 'asc' })
    expect(sort.review).toEqual({ by: 'document_id', order: 'desc' })
  })

  it('setSort persists to sessionStorage', () => {
    useAnnotateStore.getState().setSort('review', { by: 'editors_count', order: 'desc' })
    const raw = sessionStorage.getItem('annotate.store.v4')
    expect(raw).toContain('editors_count')
  })
})

describe('isSortAvailable', () => {
  it('column-only keys are available on every tab', () => {
    for (const tab of ['new', 'review', 'verified'] as const) {
      expect(isSortAvailable(tab, 'document_id')).toBe(true)
      expect(isSortAvailable(tab, 'tarih')).toBe(true)
      expect(isSortAvailable(tab, 'konu')).toBe(true)
      expect(isSortAvailable(tab, 'shuffle')).toBe(true)
    }
  })

  it('annotation-derived keys are gated to review + verified only', () => {
    expect(isSortAvailable('new', 'updated_at')).toBe(false)
    expect(isSortAvailable('new', 'editors_count')).toBe(false)
    expect(isSortAvailable('review', 'updated_at')).toBe(true)
    expect(isSortAvailable('verified', 'editors_count')).toBe(true)
  })
})
