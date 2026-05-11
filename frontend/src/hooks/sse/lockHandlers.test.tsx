import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { QueryClient } from '@tanstack/react-query'
import { registerLockHandlers } from './lockHandlers'

function makeFakeES() {
  const listeners: Record<string, Array<(e: MessageEvent) => void>> = {}
  return {
    addEventListener(type: string, fn: (e: MessageEvent) => void) {
      listeners[type] = [...(listeners[type] ?? []), fn]
    },
    dispatch(type: string, dataObj: unknown) {
      const e = new MessageEvent(type, { data: JSON.stringify(dataObj) })
      for (const fn of listeners[type] ?? []) fn(e)
    },
    dispatchRaw(type: string, raw: string) {
      const e = new MessageEvent(type, { data: raw })
      for (const fn of listeners[type] ?? []) fn(e)
    },
  }
}

describe('registerLockHandlers', () => {
  let qc: { invalidateQueries: ReturnType<typeof vi.fn> }
  let navigate: ReturnType<typeof vi.fn>
  let toastError: ReturnType<typeof vi.fn>

  beforeEach(() => {
    qc = { invalidateQueries: vi.fn() }
    navigate = vi.fn()
    toastError = vi.fn()
    Object.defineProperty(window, 'location', {
      value: { pathname: '/docs/doc-1' },
      writable: true,
    })
  })

  it('on lock_acquired by another user on current doc: toast + navigate("/")', () => {
    const es = makeFakeES()
    registerLockHandlers(es as never, {
      qc: qc as unknown as QueryClient,
      navigate, meId: 5,
      acquiringRef: { current: null },
      toast: { error: toastError } as never,
    })
    es.dispatch('lock_acquired', {
      document_id: 'doc-1', by_user_id: 6, by_username: 'someone',
    })
    expect(toastError).toHaveBeenCalledWith(expect.stringContaining('someone'))
    expect(navigate).toHaveBeenCalledWith('/', { replace: true })
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['feed'] })
  })

  it('on lock_acquired by SELF: invalidate only, no navigate', () => {
    const es = makeFakeES()
    registerLockHandlers(es as never, {
      qc: qc as unknown as QueryClient, navigate, meId: 5,
      acquiringRef: { current: null }, toast: { error: toastError } as never,
    })
    es.dispatch('lock_acquired', {
      document_id: 'doc-1', by_user_id: 5, by_username: 'me',
    })
    expect(navigate).not.toHaveBeenCalled()
    expect(toastError).not.toHaveBeenCalled()
    expect(qc.invalidateQueries).toHaveBeenCalled()
  })

  it('skips navigate when the user is currently acquiring this doc', () => {
    const es = makeFakeES()
    registerLockHandlers(es as never, {
      qc: qc as unknown as QueryClient, navigate, meId: 5,
      acquiringRef: { current: 'doc-1' },
      toast: { error: toastError } as never,
    })
    es.dispatch('lock_acquired', {
      document_id: 'doc-1', by_user_id: 6, by_username: 'someone',
    })
    expect(navigate).not.toHaveBeenCalled()
  })

  it('lock_released invalidates feed', () => {
    const es = makeFakeES()
    registerLockHandlers(es as never, {
      qc: qc as unknown as QueryClient, navigate, meId: 5,
      acquiringRef: { current: null }, toast: { error: toastError } as never,
    })
    es.dispatch('lock_released', { document_id: 'doc-1' })
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['feed'] })
  })

  it('ignores malformed payload silently', () => {
    const es = makeFakeES()
    registerLockHandlers(es as never, {
      qc: qc as unknown as QueryClient, navigate, meId: 5,
      acquiringRef: { current: null }, toast: { error: toastError } as never,
    })
    es.dispatchRaw('lock_acquired', 'not-json')
    expect(navigate).not.toHaveBeenCalled()
    expect(toastError).not.toHaveBeenCalled()
  })
})
