import { describe, it, expect, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useBeforeUnload } from './useBeforeUnload'

describe('useBeforeUnload', () => {
  it('attaches listener when enabled=true', () => {
    const addSpy = vi.spyOn(window, 'addEventListener')
    renderHook(() => useBeforeUnload(true))
    expect(addSpy).toHaveBeenCalledWith('beforeunload', expect.any(Function))
  })

  it('does not attach listener when enabled=false', () => {
    const addSpy = vi.spyOn(window, 'addEventListener')
    renderHook(() => useBeforeUnload(false))
    const calls = addSpy.mock.calls.filter((c) => c[0] === 'beforeunload')
    expect(calls).toHaveLength(0)
  })

  it('detaches listener on unmount', () => {
    const removeSpy = vi.spyOn(window, 'removeEventListener')
    const { unmount } = renderHook(() => useBeforeUnload(true))
    unmount()
    expect(removeSpy).toHaveBeenCalledWith('beforeunload', expect.any(Function))
  })

  it('handler calls preventDefault and sets returnValue', () => {
    let captured: ((e: BeforeUnloadEvent) => void) | null = null
    vi.spyOn(window, 'addEventListener').mockImplementation((evt, fn) => {
      if (evt === 'beforeunload') captured = fn as (e: BeforeUnloadEvent) => void
    })
    renderHook(() => useBeforeUnload(true, 'Devam ediyorsun'))
    expect(captured).not.toBeNull()
    const evt = { preventDefault: vi.fn(), returnValue: '' } as unknown as BeforeUnloadEvent
    captured!(evt)
    expect(evt.preventDefault).toHaveBeenCalled()
    expect(evt.returnValue).toBe('Devam ediyorsun')
  })
})
