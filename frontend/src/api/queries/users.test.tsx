/* eslint-disable react/display-name -- test wrappers, no display name needed */
import { describe, it, expect } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { useOnlineUsers, usersKeys } from './users'

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('useOnlineUsers', () => {
  it('fetches and parses the online list', async () => {
    server.use(
      http.get('http://localhost/api/users/online', () =>
        HttpResponse.json([
          { id: 1, username: 'tester', avatar_color: '#3b82f6' },
          { id: 2, username: 'admin', avatar_color: '#ef4444' },
        ])),
    )
    const { result } = renderHook(() => useOnlineUsers(), { wrapper: wrap() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.length).toBe(2)
  })

  it('exposes stable query key', () => {
    expect(usersKeys.online()).toEqual(['users', 'online'])
  })

  it('returns isError when payload is malformed', async () => {
    server.use(
      http.get('http://localhost/api/users/online', () =>
        HttpResponse.json({ broken: 'object' })),
    )
    const { result } = renderHook(() => useOnlineUsers(), { wrapper: wrap() })
    await waitFor(() => expect(result.current.isError).toBe(true))
  })
})
