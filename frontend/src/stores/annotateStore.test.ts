import { describe, it, expect, beforeEach } from 'vitest'
import { useAnnotateStore, isSortAvailable } from './annotateStore'

beforeEach(() => {
  sessionStorage.clear()
  useAnnotateStore.setState({
    currentTab: 'new',
    sort: {
      new: { by: 'tarih', order: 'desc' },
      review: { by: 'updated_at', order: 'desc' },
      verified: { by: 'updated_at', order: 'desc' },
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
    expect(sessionStorage.getItem('annotate.store.v3')).toContain('review')
  })

  it('only accepts valid tabs', () => {
    useAnnotateStore.getState().setCurrentTab('verified')
    expect(useAnnotateStore.getState().currentTab).toBe('verified')
  })

  it('initial sort per tab uses the meaningful default (not shuffle)', () => {
    const { sort } = useAnnotateStore.getState()
    expect(sort.new).toEqual({ by: 'tarih', order: 'desc' })
    expect(sort.review).toEqual({ by: 'updated_at', order: 'desc' })
    expect(sort.verified).toEqual({ by: 'updated_at', order: 'desc' })
  })

  it('setSort mutates a single tab without touching the others', () => {
    useAnnotateStore.getState().setSort('new', { by: 'konu', order: 'asc' })
    const { sort } = useAnnotateStore.getState()
    expect(sort.new).toEqual({ by: 'konu', order: 'asc' })
    expect(sort.review).toEqual({ by: 'updated_at', order: 'desc' })
  })

  it('setSort persists to sessionStorage', () => {
    useAnnotateStore.getState().setSort('review', { by: 'editors_count', order: 'desc' })
    const raw = sessionStorage.getItem('annotate.store.v3')
    expect(raw).toContain('editors_count')
  })
})

describe('isSortAvailable', () => {
  it('column-only keys are available on every tab', () => {
    for (const tab of ['new', 'review', 'verified'] as const) {
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
