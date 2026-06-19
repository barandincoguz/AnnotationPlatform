import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { useAuthStore } from '@/stores/authStore'
import { useLock } from './useLock'
import { StrictMode, type ReactNode } from 'react'

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

function strictWrapper({ children }: { children: ReactNode }) {
  return <StrictMode>{wrapper({ children })}</StrictMode>
}

const seedUser = (overrides: Partial<{ id: number; username: string }> = {}) => {
  useAuthStore.getState().setUser({
    id: 1,
    username: 'tester',
    email: null,
    role: 'user',
    is_active: true,
    has_seen_manual: true,
    has_passed_training: true,
    avatar_color: null,
    created_at: '2026-05-01T00:00:00+00:00',
    ...overrides,
  })
}

describe('useLock', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    useAuthStore.setState({ status: 'loading', user: null, error: null })
  })
  afterEach(async () => {
    cleanup()
    await vi.runOnlyPendingTimersAsync()
    vi.useRealTimers()
  })

  it('acquires on mount → status="held"', async () => {
    seedUser()
    const { result } = renderHook(() => useLock('doc-1'), { wrapper })
    await waitFor(() => expect(result.current.status).toBe('held'))
    expect(result.current.info).not.toBeNull()
  })

  it('does not release the current lock during a same-owner StrictMode remount', async () => {
    seedUser()
    let acquireCount = 0
    const releaseSpy = vi.fn(() => HttpResponse.json({ ok: true }))
    server.use(
      http.post('http://localhost/api/locks/doc-1/acquire', () => {
        acquireCount += 1
        return HttpResponse.json({
          document_id: 'doc-1',
          user_id: 1,
          by_username: 'tester',
          acquired_at: '2026-05-11T10:00:00+00:00',
          expires_at: '2026-05-11T10:01:30+00:00',
        })
      }),
      http.post('http://localhost/api/locks/doc-1/release', releaseSpy),
    )

    const { result } = renderHook(() => useLock('doc-1'), { wrapper: strictWrapper })
    await waitFor(() => expect(result.current.status).toBe('held'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })

    expect(acquireCount).toBeGreaterThanOrEqual(2)
    expect(releaseSpy).not.toHaveBeenCalled()
  })

  it('releases the old document when the hook moves to another document', async () => {
    seedUser()
    const releaseDocOne = vi.fn(() => HttpResponse.json({ ok: true }))
    server.use(
      http.post('http://localhost/api/locks/doc-1/release', releaseDocOne),
    )

    const { result, rerender } = renderHook(
      ({ documentId }) => useLock(documentId),
      { initialProps: { documentId: 'doc-1' }, wrapper },
    )
    await waitFor(() => expect(result.current.status).toBe('held'))

    rerender({ documentId: 'doc-2' })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    await waitFor(() => expect(result.current.status).toBe('held'))

    expect(releaseDocOne).toHaveBeenCalledTimes(1)
    expect(result.current.info?.document_id).toBe('doc-2')
  })

  it('409 → status="conflict" with conflict detail', async () => {
    seedUser({ id: 1 })
    server.use(
      http.post('http://localhost/api/locks/doc-1/acquire', () =>
        HttpResponse.json(
          {
            detail: {
              error: 'lock_held_by_other',
              by_user_id: 99,
              by_username: 'ahmet',
              acquired_at: '2026-05-11T10:00:00+00:00',
              expires_at: '2026-05-11T10:01:30+00:00',
            },
          },
          { status: 409 },
        ),
      ),
    )
    const { result } = renderHook(() => useLock('doc-1'), { wrapper })
    await waitFor(() => expect(result.current.status).toBe('conflict'))
    expect(result.current.conflictUsername).toBe('ahmet')
    expect(result.current.conflictIsSameUser).toBe(false)
  })

  it('same-user 409 sets conflictIsSameUser=true (F8)', async () => {
    seedUser({ id: 1 })
    server.use(
      http.post('http://localhost/api/locks/doc-1/acquire', () =>
        HttpResponse.json(
          {
            detail: {
              error: 'lock_held_by_other',
              by_user_id: 1,
              by_username: 'tester',
              acquired_at: '2026-05-11T10:00:00+00:00',
              expires_at: '2026-05-11T10:01:30+00:00',
            },
          },
          { status: 409 },
        ),
      ),
    )
    const { result } = renderHook(() => useLock('doc-1'), { wrapper })
    await waitFor(() => expect(result.current.status).toBe('conflict'))
    expect(result.current.conflictIsSameUser).toBe(true)
  })

  it('non-conflict acquire error exposes retry and can recover', async () => {
    seedUser()
    let attempts = 0
    server.use(
      http.post('http://localhost/api/locks/doc-1/acquire', () => {
        attempts++
        if (attempts === 1) {
          return HttpResponse.json({ detail: 'temporary failure' }, { status: 503 })
        }
        return HttpResponse.json({
          document_id: 'doc-1',
          user_id: 1,
          by_username: 'tester',
          acquired_at: '2026-05-11T10:00:00+00:00',
          expires_at: '2026-05-11T10:01:30+00:00',
        })
      }),
    )
    const { result } = renderHook(() => useLock('doc-1'), { wrapper })
    await waitFor(() => expect(result.current.status).toBe('error'))

    act(() => result.current.retry())

    await waitFor(() => expect(result.current.status).toBe('held'))
    expect(attempts).toBe(2)
  })

  it('does not release a lock this hook never acquired', async () => {
    seedUser({ id: 1 })
    const releaseSpy = vi.fn(() => HttpResponse.json({ ok: true }))
    server.use(
      http.post('http://localhost/api/locks/doc-1/acquire', () =>
        HttpResponse.json(
          {
            detail: {
              error: 'lock_held_by_other',
              by_user_id: 1,
              by_username: 'tester',
              acquired_at: '2026-05-11T10:00:00+00:00',
              expires_at: '2026-05-11T10:01:30+00:00',
            },
          },
          { status: 409 },
        ),
      ),
      http.post('http://localhost/api/locks/doc-1/release', releaseSpy),
    )
    const { result, unmount } = renderHook(() => useLock('doc-1'), { wrapper })
    await waitFor(() => expect(result.current.status).toBe('conflict'))

    unmount()
    await act(async () => {
      await Promise.resolve()
    })

    expect(releaseSpy).not.toHaveBeenCalled()
  })

  it('heartbeat 404 → status="lost" (B6)', async () => {
    seedUser()
    let heartbeats = 0
    server.use(
      http.post('http://localhost/api/locks/doc-1/heartbeat', () => {
        heartbeats++
        return HttpResponse.json({ detail: 'not lock holder' }, { status: 404 })
      }),
    )
    const { result } = renderHook(() => useLock('doc-1'), { wrapper })
    await waitFor(() => expect(result.current.status).toBe('held'))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(35_000)
    })
    await waitFor(() => expect(result.current.status).toBe('lost'))
    expect(heartbeats).toBeGreaterThan(0)
  })

  it('explicit release transitions to status="released"', async () => {
    seedUser()
    const releaseSpy = vi.fn(() => HttpResponse.json({ ok: true }))
    server.use(
      http.post('http://localhost/api/locks/doc-1/release', releaseSpy),
    )
    const { result, unmount } = renderHook(() => useLock('doc-1'), { wrapper })
    await waitFor(() => expect(result.current.status).toBe('held'))
    await act(async () => {
      await result.current.release()
    })
    expect(result.current.status).toBe('released')

    unmount()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    expect(releaseSpy).toHaveBeenCalledTimes(1)
  })

  it('explicit release rejects on an HTTP error and keeps the held state', async () => {
    seedUser()
    server.use(
      http.post('http://localhost/api/locks/doc-1/release', () =>
        HttpResponse.json({ detail: 'not lock holder' }, { status: 404 }),
      ),
    )
    const { result } = renderHook(() => useLock('doc-1'), { wrapper })
    await waitFor(() => expect(result.current.status).toBe('held'))

    await expect(result.current.release()).rejects.toThrow('release_failed')
    expect(result.current.status).toBe('held')
  })

  it('unmount clears heartbeat interval (B2)', async () => {
    seedUser()
    let heartbeats = 0
    server.use(
      http.post('http://localhost/api/locks/doc-1/heartbeat', () => {
        heartbeats++
        return HttpResponse.json({
          document_id: 'doc-1',
          user_id: 1,
          by_username: 'tester',
          acquired_at: '2026-05-11T10:00:00+00:00',
          expires_at: '2026-05-11T10:01:30+00:00',
        })
      }),
    )
    const { result, unmount } = renderHook(() => useLock('doc-1'), { wrapper })
    await waitFor(() => expect(result.current.status).toBe('held'))
    unmount()
    const before = heartbeats
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })
    expect(heartbeats).toBe(before)
  })
})
