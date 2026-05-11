import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { QueryClient } from '@tanstack/react-query'
import { registerFeedHandlers } from './feedHandlers'

function makeFakeES() {
  const listeners: Record<string, ((e: MessageEvent) => void)[]> = {}
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

describe('registerFeedHandlers', () => {
  let qc: { invalidateQueries: ReturnType<typeof vi.fn> }

  beforeEach(() => {
    qc = { invalidateQueries: vi.fn() }
  })

  it('annotation_saved invalidates feed', () => {
    const es = makeFakeES()
    registerFeedHandlers(es as never, { qc: qc as unknown as QueryClient })
    es.dispatch('annotation_saved', { document_id: 'doc-1', user_id: 1 })
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['feed'] })
  })

  it('ignores malformed payload', () => {
    const es = makeFakeES()
    registerFeedHandlers(es as never, { qc: qc as unknown as QueryClient })
    es.dispatchRaw('annotation_saved', 'not-json')
    expect(qc.invalidateQueries).not.toHaveBeenCalled()
  })
})
