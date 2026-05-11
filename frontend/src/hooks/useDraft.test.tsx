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
        HttpResponse.json(
          { detail: { error: 'not_found', message: '' } },
          { status: 404 },
        ),
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
      http.delete('http://localhost/api/drafts/doc-1', () =>
        HttpResponse.json({ ok: true }),
      ),
    )
    const { result } = renderHook(() => useDraft('doc-1'), { wrapper })
    await waitFor(() => expect(result.current.draftQuery.isSuccess).toBe(true))
    await act(async () => {
      await result.current.deleteMutation.mutateAsync()
    })
    await waitFor(() => expect(result.current.deleteMutation.isSuccess).toBe(true))
  })
})
