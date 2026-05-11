import { describe, it, expect, vi } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import {
  useUnreadNotifications, useNotificationsHistory,
  useMarkReadMutation, useMarkAllReadMutation, notificationsKeys,
} from './notifications'
import { toast } from 'sonner'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

function wrap() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return {
    qc,
    Wrapper: ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    ),
  }
}

function makeNotif(over: Partial<{ id: number; is_read: boolean; kind: string; title: string }> = {}) {
  return {
    id: 1, kind: 'admin_announcement', title: 'Hello', body: null,
    data: null, is_read: false, created_at: '2026-05-11T00:00:00+00:00',
    ...over,
  }
}

describe('useUnreadNotifications', () => {
  it('fetches with unread_only=true & limit=50', async () => {
    let calledWith: URL | null = null
    server.use(
      http.get('http://localhost/api/me/notifications', ({ request }) => {
        calledWith = new URL(request.url)
        return HttpResponse.json({ items: [makeNotif()] })
      }),
    )
    const { Wrapper } = wrap()
    const { result } = renderHook(() => useUnreadNotifications(), { wrapper: Wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.items.length).toBe(1)
    expect(calledWith?.searchParams.get('unread_only')).toBe('true')
    expect(calledWith?.searchParams.get('limit')).toBe('50')
  })
})

describe('useNotificationsHistory', () => {
  it('fetches with unread_only=false', async () => {
    let calledWith: URL | null = null
    server.use(
      http.get('http://localhost/api/me/notifications', ({ request }) => {
        calledWith = new URL(request.url)
        return HttpResponse.json({ items: [] })
      }),
    )
    const { Wrapper } = wrap()
    const { result } = renderHook(() => useNotificationsHistory(), { wrapper: Wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(calledWith?.searchParams.get('unread_only')).toBe('false')
  })
})

describe('useMarkReadMutation', () => {
  it('POSTs /{id}/read and invalidates the notifications cache', async () => {
    let posted: string | null = null
    server.use(
      http.post('http://localhost/api/me/notifications/:id/read', ({ params }) => {
        posted = String(params.id)
        return HttpResponse.json({ ok: true })
      }),
    )
    const { qc, Wrapper } = wrap()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = renderHook(() => useMarkReadMutation(), { wrapper: Wrapper })
    await act(async () => { await result.current.mutateAsync(42) })
    expect(posted).toBe('42')
    expect(spy).toHaveBeenCalledWith({ queryKey: notificationsKeys.all })
  })
})

describe('useMarkAllReadMutation', () => {
  it('POSTs /read-all and shows toast with marked_count', async () => {
    server.use(
      http.post('http://localhost/api/me/notifications/read-all', () =>
        HttpResponse.json({ marked_count: 7 })),
    )
    const { Wrapper } = wrap()
    const { result } = renderHook(() => useMarkAllReadMutation(), { wrapper: Wrapper })
    await act(async () => { await result.current.mutateAsync() })
    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('7'))
  })

  it('surfaces Zod parse failure as mutation error (no toast)', async () => {
    server.use(
      http.post('http://localhost/api/me/notifications/read-all', () =>
        HttpResponse.json({ broken: true })),
    )
    const { Wrapper } = wrap()
    const { result } = renderHook(() => useMarkAllReadMutation(), { wrapper: Wrapper })
    await act(async () => {
      await result.current.mutateAsync().catch(() => null)
    })
    expect(result.current.isError).toBe(true)
  })
})
