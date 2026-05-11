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
    const removeEventListenerImpl = (_evt: string, _fn: EventListenerOrEventListenerObject) => {
      // Mock implementation for removeEventListener
    }
    const removeSpy = vi.spyOn(window, 'removeEventListener').mockImplementation(removeEventListenerImpl)
    const { unmount } = renderHook(() => useBeforeUnload(true))
    unmount()
    expect(removeSpy).toHaveBeenCalledWith('beforeunload', expect.any(Function))
  })

  it('handler calls preventDefault and sets returnValue', () => {
    let captured: ((e: BeforeUnloadEvent) => void) | null = null
    const addEventListenerImpl = (evt: string, fn: EventListenerOrEventListenerObject) => {
      if (evt === 'beforeunload') captured = fn as (e: BeforeUnloadEvent) => void
    }
    vi.spyOn(window, 'addEventListener').mockImplementation(addEventListenerImpl)
    renderHook(() => useBeforeUnload(true, 'Devam ediyorsun'))
    expect(captured).not.toBeNull()
    const preventDefaultFn = vi.fn()
    const evt = { preventDefault: preventDefaultFn, returnValue: '' } as unknown as BeforeUnloadEvent
    captured!(evt)
    expect(preventDefaultFn).toHaveBeenCalled()
    expect(evt.returnValue).toBe('Devam ediyorsun')
  })
})
