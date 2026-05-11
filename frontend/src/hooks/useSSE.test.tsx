import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useSSE } from './useSSE'
import { useAuthStore } from '@/stores/authStore'

class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {}
  readyState = 1
  onerror: (() => void) | null = null
  closed = false
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 2

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }
  addEventListener(type: string, cb: (e: MessageEvent) => void) {
    ;(this.listeners[type] ??= []).push(cb)
  }
  close() {
    this.closed = true
    this.readyState = MockEventSource.CLOSED
  }
  emit(type: string, data: unknown) {
    for (const cb of this.listeners[type] ?? []) {
      cb(new MessageEvent(type, { data: JSON.stringify(data) }))
    }
  }
}

beforeEach(() => {
  MockEventSource.instances = []
  // @ts-expect-error mock global
  globalThis.EventSource = MockEventSource
  useAuthStore.getState().setUser({
    id: 1, username: 'tester', email: null, role: 'user',
    is_active: true, has_seen_manual: true, has_passed_training: true,
    avatar_color: null, created_at: '2026-05-01T00:00:00+00:00',
  })
})
afterEach(() => {
  useAuthStore.setState({ status: 'loading', user: null, error: null })
})

function wrapper({ children, qc }: { children: ReactNode; qc: QueryClient }) {
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/']}>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('useSSE', () => {
  it('opens EventSource on mount and closes on unmount (B5)', () => {
    const qc = new QueryClient()
    const { unmount } = renderHook(() => useSSE({ acquiringDocId: null }), {
      wrapper: ({ children }) => wrapper({ children, qc }),
    })
    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0]!.url).toBe('/api/events')
    unmount()
    expect(MockEventSource.instances[0]!.closed).toBe(true)
  })

  it('lock_acquired invalidates feed', async () => {
    const qc = new QueryClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    renderHook(() => useSSE({ acquiringDocId: null }), {
      wrapper: ({ children }) => wrapper({ children, qc }),
    })
    act(() => {
      MockEventSource.instances[0]!.emit('lock_acquired', {
        document_id: 'foo', by_user_id: 99, by_username: 'ahmet',
      })
    })
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith({ queryKey: ['feed'] }),
    )
  })

  it('lock_released invalidates feed', async () => {
    const qc = new QueryClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    renderHook(() => useSSE({ acquiringDocId: null }), {
      wrapper: ({ children }) => wrapper({ children, qc }),
    })
    act(() => {
      MockEventSource.instances[0]!.emit('lock_released', {
        document_id: 'foo', by_user_id: 99,
      })
    })
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith({ queryKey: ['feed'] }),
    )
  })

  it('lock_acquired for own user does NOT trigger kick-out toast', () => {
    const qc = new QueryClient()
    renderHook(() => useSSE({ acquiringDocId: null }), {
      wrapper: ({ children }) => wrapper({ children, qc }),
    })
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { pathname: '/docs/foo' },
    })
    expect(() => {
      act(() => {
        MockEventSource.instances[0]!.emit('lock_acquired', {
          document_id: 'foo', by_user_id: 1, by_username: 'tester',
        })
      })
    }).not.toThrow()
  })

  it('lock_acquired during own acquire is ignored (F1)', () => {
    const qc = new QueryClient()
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { pathname: '/docs/foo' },
    })
    renderHook(() => useSSE({ acquiringDocId: 'foo' }), {
      wrapper: ({ children }) => wrapper({ children, qc }),
    })
    expect(() => {
      act(() => {
        MockEventSource.instances[0]!.emit('lock_acquired', {
          document_id: 'foo', by_user_id: 99, by_username: 'ahmet',
        })
      })
    }).not.toThrow()
  })
})
