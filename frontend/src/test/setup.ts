import '@testing-library/jest-dom/vitest'
import { afterAll, afterEach, beforeAll, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import { server } from './msw-server'
import { useAuthStore } from '@/stores/authStore'
import { setNavigator, setAuthHandlers, _resetHydrationStateForTests } from '@/api/client'

class NoopEventSource {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 2
  readyState = 0
  url: string
  constructor(url: string) {
    this.url = url
  }
  addEventListener(): void {
    return undefined
  }
  removeEventListener(): void {
    return undefined
  }
  close(): void {
    return undefined
  }
  onerror = null
}
// @ts-expect-error mock global
globalThis.EventSource = NoopEventSource

if (!globalThis.localStorage || typeof globalThis.localStorage.setItem !== 'function') {
  const store = new Map<string, string>()
  const storageMock = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, val: string) => store.set(key, String(val)),
    removeItem: (key: string) => store.delete(key),
    clear: () => store.clear(),
    key: (i: number) => Array.from(store.keys())[i] ?? null,
    get length() {
      return store.size
    },
  }
  Object.defineProperty(globalThis, 'localStorage', {
    value: storageMock,
    writable: true,
  })
  if (typeof window !== 'undefined') {
    Object.defineProperty(window, 'localStorage', {
      value: storageMock,
      writable: true,
    })
  }
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))

afterEach(() => {
  server.resetHandlers()
  cleanup()
  useAuthStore.setState({ status: 'loading', user: null, error: null })
  setNavigator(null)
  setAuthHandlers(null)
  _resetHydrationStateForTests()
  vi.restoreAllMocks()
})

afterAll(() => server.close())

/** Opt-in helper for tests that intentionally trigger React errors. */
export function silenceConsoleError() {
  return vi.spyOn(console, 'error').mockImplementation(() => undefined)
}
