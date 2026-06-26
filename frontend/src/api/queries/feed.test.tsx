/* eslint-disable react/display-name -- test wrappers, no display name needed */
import { describe, it, expect } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { makeFeedItem } from '@/test/msw-handlers'
import { useFeedInfinite } from './feed'

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('useFeedInfinite', () => {
  it('uses first-page total to request the next page with offset 50', async () => {
    const offsets: number[] = []
    server.use(
      http.get('http://localhost/api/feed', ({ request }) => {
        const url = new URL(request.url)
        const offset = Number(url.searchParams.get('offset') ?? '0')
        offsets.push(offset)
        const base = offset === 0 ? 0 : 50
        return HttpResponse.json({
          items: Array.from({ length: 50 }, (_, i) =>
            makeFeedItem({
              document_id: `doc-${base + i}`,
              workflow_state: 'verified',
              is_completed: true,
            }),
          ),
          total: offset === 0 ? 683 : null,
        })
      }),
    )

    const { result } = renderHook(
      () => useFeedInfinite('verified', { by: 'document_id', order: 'desc' }),
      { wrapper: wrap() },
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.hasNextPage).toBe(true)

    let nextPageResult: Awaited<ReturnType<typeof result.current.fetchNextPage>> | undefined
    await act(async () => {
      nextPageResult = await result.current.fetchNextPage()
    })

    expect(offsets).toEqual([0, 50])
    expect(nextPageResult?.data?.pages).toHaveLength(2)
    expect(nextPageResult?.data?.pages.flatMap((page) => page.items)).toHaveLength(100)
  })
})
