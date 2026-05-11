import { describe, it, expect, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { QueryClient } from '@tanstack/react-query'
import { server } from '@/test/msw-server'
import { makeUser } from '@/test/msw-handlers'
import { useAuthStore } from '@/stores/authStore'
import { authKeys } from '@/api/queries/auth'
import { refreshAuth } from './refreshAuth'

const API = 'http://localhost'

describe('refreshAuth', () => {
  let qc: QueryClient
  beforeEach(() => {
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    useAuthStore.setState({ status: 'authed', user: null, error: null })
  })

  it('fetches /api/auth/me with staleTime 0 and updates authStore', async () => {
    const user = makeUser({ has_seen_manual: true, has_passed_training: true })
    server.use(http.get(`${API}/api/auth/me`, () => HttpResponse.json(user)))

    const fresh = await refreshAuth(qc)

    expect(fresh.has_passed_training).toBe(true)
    expect(useAuthStore.getState().user?.has_passed_training).toBe(true)
    expect(qc.getQueryData(authKeys.me)).toEqual(user)
  })

  it('throws on network error and does not mutate authStore', async () => {
    server.use(http.get(`${API}/api/auth/me`, () => HttpResponse.error()))

    await expect(refreshAuth(qc)).rejects.toBeDefined()
    expect(useAuthStore.getState().user).toBeNull()
  })
})
