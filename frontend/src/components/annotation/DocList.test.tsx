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
    await waitFor(() => expect(screen.getByText(/№\s*1/)).toBeInTheDocument())
    expect(screen.getByText(/№\s*2/)).toBeInTheDocument()
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
