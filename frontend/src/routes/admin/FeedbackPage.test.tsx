import { beforeAll, describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { server } from '@/test/msw-server'
import { makeFeedbackRow } from '@/test/msw-handlers'
import { FeedbackPage } from './FeedbackPage'

beforeAll(() => {
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = () => false
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = () => undefined
  }
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => undefined
  }
})

const Wrap = () => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter
      initialEntries={['/admin/feedback']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <FeedbackPage />
    </MemoryRouter>
  </QueryClientProvider>
)

describe('FeedbackPage', () => {
  it('renders feedback rows with type badges', async () => {
    server.use(
      http.get('http://localhost/api/admin/feedback', () =>
        HttpResponse.json([
          makeFeedbackRow({ id: 1, username: 'alice', type: 'complaint', message: 'Kilit açılmıyor' }),
          makeFeedbackRow({ id: 2, username: 'bob', type: 'suggestion', message: 'Filtre eklensin' }),
        ]),
      ),
    )

    render(<Wrap />)

    await waitFor(() => expect(screen.getByText('alice')).toBeInTheDocument())
    expect(screen.getByText('bob')).toBeInTheDocument()
    expect(screen.getByText('Kilit açılmıyor')).toBeInTheDocument()
    expect(screen.getAllByText('Şikayet').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Öneri').length).toBeGreaterThan(0)
  })

  it('filters admin list by type_filter query param', async () => {
    const seenFilters: Array<string | null> = []
    server.use(
      http.get('http://localhost/api/admin/feedback', ({ request }) => {
        const url = new URL(request.url)
        const filter = url.searchParams.get('type_filter')
        seenFilters.push(filter)
        return HttpResponse.json(
          filter === 'complaint'
            ? [makeFeedbackRow({ id: 3, type: 'complaint', message: 'Complaint only' })]
            : [makeFeedbackRow()],
        )
      }),
    )
    const user = userEvent.setup()

    render(<Wrap />)
    await waitFor(() => expect(screen.getByText(/liste ekranına hızlı filtre/i)).toBeInTheDocument())

    await user.click(screen.getByRole('combobox', { name: /tip filtresi/i }))
    await user.click(await screen.findByText('Şikayet'))

    await waitFor(() => expect(seenFilters).toContain('complaint'))
    expect(await screen.findByText('Complaint only')).toBeInTheDocument()
  })

  it('truncates and expands long messages', async () => {
    const longMessage = Array.from({ length: 24 }, () => 'Uzun mesaj.').join(' ')
    server.use(
      http.get('http://localhost/api/admin/feedback', () =>
        HttpResponse.json([makeFeedbackRow({ id: 4, message: longMessage })]),
      ),
    )
    const user = userEvent.setup()

    render(<Wrap />)

    await waitFor(() => expect(screen.getByText(/uzun mesaj/i)).toBeInTheDocument())
    expect(screen.queryByText(longMessage)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /devamını göster/i }))
    expect(screen.getByText(longMessage)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /kısalt/i }))
    expect(screen.queryByText(longMessage)).not.toBeInTheDocument()
  })

  it('shows empty state', async () => {
    server.use(
      http.get('http://localhost/api/admin/feedback', () => HttpResponse.json([])),
    )

    render(<Wrap />)

    expect(await screen.findByText(/geri bildirim yok/i)).toBeInTheDocument()
  })
})
