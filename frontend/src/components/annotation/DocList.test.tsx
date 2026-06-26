import { describe, it, expect, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { renderWithProviders } from '@/test/render'
import { makeFeedItem } from '@/test/msw-handlers'
import { DocList } from './DocList'

describe('DocList', () => {
  it('renders feed items for the selected tab', async () => {
    server.use(
      http.get('http://localhost/api/feed', () =>
        HttpResponse.json({
          items: [
            makeFeedItem({ document_id: 'doc-a', sayi: 1 }),
            makeFeedItem({ document_id: 'doc-b', sayi: 2 }),
          ],
          total: 2,
        }),
      ),
    )
    renderWithProviders(<DocList tab="new" selectedId={null} onSelectDoc={vi.fn()} />)
    // List rows now lead with document_id (evrakOid) instead of the
    // dropped per-year sayi.
    await waitFor(() => expect(screen.getByText('doc-a')).toBeInTheDocument())
    expect(screen.getByText('doc-b')).toBeInTheDocument()
  })

  it('renders the total count from the feed response', async () => {
    server.use(
      http.get('http://localhost/api/feed', () =>
        HttpResponse.json({
          items: [makeFeedItem({ document_id: 'doc-a' })],
          total: 683,
        }),
      ),
    )
    renderWithProviders(<DocList tab="verified" selectedId={null} onSelectDoc={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('683 kayıt')).toBeInTheDocument())
  })

  it('shows empty state when feed is empty', async () => {
    server.use(
      http.get('http://localhost/api/feed', () => HttpResponse.json({ items: [], total: 0 })),
    )
    renderWithProviders(<DocList tab="new" selectedId={null} onSelectDoc={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/bu sekmede doküman yok/i)).toBeInTheDocument())
  })

  it('shows loading state initially', () => {
    server.use(
      http.get('http://localhost/api/feed', async () => {
        await new Promise((r) => setTimeout(r, 1000))
        return HttpResponse.json({ items: [], total: 0 })
      }),
    )
    renderWithProviders(<DocList tab="new" selectedId={null} onSelectDoc={vi.fn()} />)
    expect(screen.getByText(/yükleniyor/i)).toBeInTheDocument()
  })

  it('calls onSelectDoc with the doc id when an item is clicked', async () => {
    const onSelect = vi.fn()
    server.use(
      http.get('http://localhost/api/feed', () =>
        HttpResponse.json({
          items: [makeFeedItem({ document_id: 'doc-A' })],
          total: 1,
        }),
      ),
    )
    renderWithProviders(<DocList tab="new" selectedId={null} onSelectDoc={onSelect} />)
    await waitFor(() => expect(screen.getByRole('button')).toBeInTheDocument())
    screen.getByRole('button').click()
    expect(onSelect).toHaveBeenCalledWith('doc-A')
  })
})
