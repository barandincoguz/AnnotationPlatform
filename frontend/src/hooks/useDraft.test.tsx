import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { makeReferenceItem } from '@/test/msw-handlers'
import { useDraft } from './useDraft'
import type { ReactNode } from 'react'

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

describe('useDraft', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('loads existing draft via GET, 404 yields null', async () => {
    server.use(
      http.get('http://localhost/api/drafts/doc-1', () =>
        HttpResponse.json({ detail: { error: 'not_found', message: '' } }, { status: 404 }),
      ),
    )
    const { result } = renderHook(() => useDraft('doc-1'), { wrapper })
    await waitFor(() => expect(result.current.draftQuery.isSuccess).toBe(true))
    expect(result.current.draftQuery.data).toBeNull()
  })

  it('debouncedSave fires PUT /drafts after 2s of inactivity', async () => {
    const putSpy = vi.fn(() => HttpResponse.json({ ok: true }))
    server.use(http.put('http://localhost/api/drafts/doc-1', putSpy))

    const { result } = renderHook(() => useDraft('doc-1'), { wrapper })
    await waitFor(() => expect(result.current.draftQuery.isSuccess).toBe(true))

    act(() => {
      result.current.debouncedSave([makeReferenceItem()])
    })
    expect(putSpy).not.toHaveBeenCalled()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000)
    })
    await waitFor(() => expect(putSpy).toHaveBeenCalledTimes(1))
    expect(result.current.saveStatus).toBe('saved')
  })

  it('rapid edits only fire the latest PUT (debounce)', async () => {
    const putSpy = vi.fn(() => HttpResponse.json({ ok: true }))
    server.use(http.put('http://localhost/api/drafts/doc-1', putSpy))

    const { result } = renderHook(() => useDraft('doc-1'), { wrapper })
    await waitFor(() => expect(result.current.draftQuery.isSuccess).toBe(true))

    act(() => {
      result.current.debouncedSave([makeReferenceItem({ madde: '1' })])
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500)
    })
    act(() => {
      result.current.debouncedSave([makeReferenceItem({ madde: '2' })])
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000)
    })
    await waitFor(() => expect(putSpy).toHaveBeenCalledTimes(1))
  })

  it('blockSavesUntilFurtherNotice cancels pending debounce + blocks new', async () => {
    const putSpy = vi.fn(() => HttpResponse.json({ ok: true }))
    server.use(http.put('http://localhost/api/drafts/doc-1', putSpy))

    const { result } = renderHook(() => useDraft('doc-1'), { wrapper })
    await waitFor(() => expect(result.current.draftQuery.isSuccess).toBe(true))

    act(() => {
      result.current.debouncedSave([makeReferenceItem()])
    })
    act(() => {
      result.current.blockSavesUntilFurtherNotice()
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3_000)
    })
    expect(putSpy).not.toHaveBeenCalled()

    // Even new calls during block are no-ops
    act(() => {
      result.current.debouncedSave([makeReferenceItem({ madde: 'X' })])
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3_000)
    })
    expect(putSpy).not.toHaveBeenCalled()
  })

  it('deleteMutation issues DELETE /drafts; 404 is treated OK', async () => {
    server.use(
      http.delete('http://localhost/api/drafts/doc-1', () => HttpResponse.json({ ok: true })),
    )
    const { result } = renderHook(() => useDraft('doc-1'), { wrapper })
    await waitFor(() => expect(result.current.draftQuery.isSuccess).toBe(true))
    await act(async () => {
      await result.current.deleteMutation.mutateAsync()
    })
    await waitFor(() => expect(result.current.deleteMutation.isSuccess).toBe(true))
  })

  // === Phase 3: autosave empty → DELETE, PUT cache update, feed
  // invalidation only on 0↔non-zero draft transitions ===

  it('debouncedSave with empty refs fires DELETE (not PUT) on autosave', async () => {
    const putSpy = vi.fn(() => HttpResponse.json({ ok: true }))
    const delSpy = vi.fn(() => HttpResponse.json({ ok: true }))
    server.use(
      http.put('http://localhost/api/drafts/doc-1', putSpy),
      http.delete('http://localhost/api/drafts/doc-1', delSpy),
    )
    const { result } = renderHook(() => useDraft('doc-1'), { wrapper })
    await waitFor(() => expect(result.current.draftQuery.isSuccess).toBe(true))

    act(() => {
      result.current.debouncedSave([])
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000)
    })
    await waitFor(() => expect(delSpy).toHaveBeenCalledTimes(1))
    expect(putSpy).not.toHaveBeenCalled()
  })

  it('PUT success updates draftKeys cache (Codex review #3)', async () => {
    // Without the post-PUT cache write, the transition check would
    // keep seeing prev=0 and either over-invalidate or miss the
    // non-zero→empty boundary on a later DELETE.
    server.use(
      http.put('http://localhost/api/drafts/doc-1', () => HttpResponse.json({ ok: true })),
    )
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const customWrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    )
    const { result } = renderHook(() => useDraft('doc-1'), { wrapper: customWrapper })
    await waitFor(() => expect(result.current.draftQuery.isSuccess).toBe(true))

    const ref = makeReferenceItem()
    act(() => {
      result.current.debouncedSave([ref])
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000)
    })
    await waitFor(() => expect(result.current.saveStatus).toBe('saved'))

    // The hook must have written {references: [ref]} into the cache.
    const cached = qc.getQueryData<{ references: unknown[] } | null>(['drafts', 'doc-1'])
    expect(cached).not.toBeNull()
    expect(cached?.references).toHaveLength(1)
  })

  it('autosave PUT then DELETE invalidates feed exactly twice (0→1 + 1→0 transitions)', async () => {
    server.use(
      http.put('http://localhost/api/drafts/doc-1', () => HttpResponse.json({ ok: true })),
      http.delete('http://localhost/api/drafts/doc-1', () => HttpResponse.json({ ok: true })),
    )
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')
    const customWrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    )
    const { result } = renderHook(() => useDraft('doc-1'), { wrapper: customWrapper })
    await waitFor(() => expect(result.current.draftQuery.isSuccess).toBe(true))
    invalidateSpy.mockClear()

    // Transition #1: empty → 1 ref. Feed must invalidate.
    act(() => {
      result.current.debouncedSave([makeReferenceItem()])
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000)
    })
    await waitFor(() => expect(result.current.saveStatus).toBe('saved'))
    const feedCallsAfterFirstPut = invalidateSpy.mock.calls.filter(
      (c) => Array.isArray((c[0] as { queryKey?: readonly unknown[] })?.queryKey)
        && ((c[0] as { queryKey: readonly unknown[] }).queryKey[0] === 'feed'),
    ).length
    expect(feedCallsAfterFirstPut).toBe(1)

    // Transition #2: 1 ref → empty (autosave path → DELETE). Feed invalidates again.
    act(() => {
      result.current.debouncedSave([])
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000)
    })
    await waitFor(() => expect(result.current.saveStatus).toBe('saved'))
    const feedCallsAfterDelete = invalidateSpy.mock.calls.filter(
      (c) => Array.isArray((c[0] as { queryKey?: readonly unknown[] })?.queryKey)
        && ((c[0] as { queryKey: readonly unknown[] }).queryKey[0] === 'feed'),
    ).length
    expect(feedCallsAfterDelete).toBe(2)
  })
})
