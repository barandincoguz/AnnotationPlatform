import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { QueryClient } from '@tanstack/react-query'
import { registerPresenceHandlers } from './presenceHandlers'

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
  }
}

describe('registerPresenceHandlers', () => {
  let qc: { invalidateQueries: ReturnType<typeof vi.fn> }

  beforeEach(() => {
    qc = { invalidateQueries: vi.fn() }
  })

  it('user_online invalidates users.online cache', () => {
    const es = makeFakeES()
    registerPresenceHandlers(es as never, { qc: qc as unknown as QueryClient })
    es.dispatch('user_online', { id: 2, username: 'x', avatar_color: '#abc' })
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['users', 'online'] })
  })

  it('user_offline invalidates users.online cache', () => {
    const es = makeFakeES()
    registerPresenceHandlers(es as never, { qc: qc as unknown as QueryClient })
    es.dispatch('user_offline', { id: 2 })
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['users', 'online'] })
  })

  it('malformed user_online payload is ignored', () => {
    const es = makeFakeES()
    registerPresenceHandlers(es as never, { qc: qc as unknown as QueryClient })
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    es.dispatch('user_online', { wrong: 'shape' })
    expect(qc.invalidateQueries).not.toHaveBeenCalled()
    warn.mockRestore()
  })
})
