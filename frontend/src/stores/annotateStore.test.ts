import { describe, it, expect, beforeEach } from 'vitest'
import { useAnnotateStore } from './annotateStore'

beforeEach(() => {
  sessionStorage.clear()
  useAnnotateStore.setState({ currentTab: 'new' })
})

describe('annotateStore', () => {
  it('defaults to "new" tab', () => {
    expect(useAnnotateStore.getState().currentTab).toBe('new')
  })

  it('setCurrentTab updates and persists to sessionStorage', () => {
    useAnnotateStore.getState().setCurrentTab('review')
    expect(useAnnotateStore.getState().currentTab).toBe('review')
    expect(sessionStorage.getItem('annotate.currentTab')).toContain('review')
  })

  it('only accepts valid tabs', () => {
    useAnnotateStore.getState().setCurrentTab('verified')
    expect(useAnnotateStore.getState().currentTab).toBe('verified')
  })
})
