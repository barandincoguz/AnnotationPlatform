import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { NotificationsList } from './NotificationsList'
import { makeNotification } from '@/test/msw-handlers'

vi.mock('sonner', () => ({ toast: { success: vi.fn() } }))

function wrap() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('NotificationsList', () => {
  it('renders empty state when history is empty', async () => {
    server.use(
      http.get('http://localhost/api/me/notifications', () =>
        HttpResponse.json({ items: [] })),
    )
    render(<NotificationsList />, { wrapper: wrap() })
    expect(await screen.findByText(/Henüz bildirim yok/)).toBeInTheDocument()
  })

  it('renders items', async () => {
    server.use(
      http.get('http://localhost/api/me/notifications', () =>
        HttpResponse.json({
          items: [
            makeNotification({ id: 1, title: 'A', is_read: false }),
            makeNotification({ id: 2, title: 'B', is_read: true }),
          ],
        })),
    )
    render(<NotificationsList />, { wrapper: wrap() })
    expect(await screen.findByText('A')).toBeInTheDocument()
    expect(screen.getByText('B')).toBeInTheDocument()
  })

  it('shows "Tümünü okundu yap" only when at least one unread item exists', async () => {
    server.use(
      http.get('http://localhost/api/me/notifications', () =>
        HttpResponse.json({
          items: [makeNotification({ id: 2, title: 'X', is_read: true })],
        })),
    )
    render(<NotificationsList />, { wrapper: wrap() })
    await screen.findByText('X')
    expect(screen.queryByText(/Tümünü okundu yap/)).not.toBeInTheDocument()
  })

  it('clicking "Tümünü okundu yap" calls mark-all endpoint', async () => {
    let posted = false
    server.use(
      http.get('http://localhost/api/me/notifications', () =>
        HttpResponse.json({
          items: [makeNotification({ id: 1, title: 'A', is_read: false })],
        })),
      http.post('http://localhost/api/me/notifications/read-all', () => {
        posted = true
        return HttpResponse.json({ marked_count: 1 })
      }),
    )
    const user = userEvent.setup()
    render(<NotificationsList />, { wrapper: wrap() })
    await screen.findByText('A')
    await user.click(screen.getByText(/Tümünü okundu yap/))
    await waitFor(() => expect(posted).toBe(true))
  })

  it('on fetch error, shows error block + retry', async () => {
    server.use(
      http.get('http://localhost/api/me/notifications', () =>
        HttpResponse.json({ broken: true }, { status: 500 })),
    )
    render(<NotificationsList />, { wrapper: wrap() })
    expect(await screen.findByText(/yüklenirken hata/i)).toBeInTheDocument()
  })
})
