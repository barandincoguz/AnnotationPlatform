import '@testing-library/jest-dom/vitest'
import { afterAll, afterEach, beforeAll, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import { server } from './msw-server'
import { useAuthStore } from '@/stores/authStore'
import {
  setNavigator,
  setAuthHandlers,
  _resetHydrationStateForTests,
} from '@/api/client'

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
