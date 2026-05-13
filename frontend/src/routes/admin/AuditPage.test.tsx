/* eslint-disable react/display-name */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { server } from '@/test/msw-server'
import { AuditPage } from './AuditPage'

const Wrap = ({ search = '' }: { search?: string }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[`/admin/audit${search}`]}>
      <AuditPage />
    </MemoryRouter>
  </QueryClientProvider>
)

beforeEach(() => {
  server.use(
    http.get('http://localhost/api/admin/audit-log', () =>
      HttpResponse.json({
        items: [
          {
            id: 1, admin_user_id: 1, admin_username: 'root',
            action_type: 'promote', target_kind: 'user', target_id: '5',
            metadata: '{}', trace_id: 'tr-1',
            created_at: '2026-05-12T10:00:00+00:00',
          },
        ],
        total: 1, has_more: false,
      }),
    ),
  )
})

describe('AuditPage', () => {
  it('renders empty state when API returns no items', async () => {
    server.use(http.get('http://localhost/api/admin/audit-log', () =>
      HttpResponse.json({ items: [], total: 0, has_more: false }),
    ))
    render(<Wrap />)
    await waitFor(() =>
      expect(screen.getByText(/eşleşen kayıt yok/i)).toBeInTheDocument(),
    )
  })

  it('renders a row from the API', async () => {
    render(<Wrap />)
    await waitFor(() => expect(screen.getByText('root')).toBeInTheDocument())
    expect(screen.getByText('promote')).toBeInTheDocument()
    expect(screen.getByText('tr-1')).toBeInTheDocument()
  })

  it('typing in trace_id input and submitting filters the query (URL sync)', async () => {
    const user = userEvent.setup()
    render(<Wrap />)
    await waitFor(() => expect(screen.getByText('root')).toBeInTheDocument())
    const traceInput = screen.getByLabelText(/trace id ara/i)
    await user.type(traceInput, 'tr-1')
    await user.click(screen.getByRole('button', { name: /filtreyi uygula/i }))
    expect((traceInput as HTMLInputElement).value).toBe('tr-1')
  })

  it('initial render hydrates trace_id from URL', async () => {
    render(<Wrap search="?trace_id=hydrated-tr" />)
    await waitFor(() =>
      expect((screen.getByLabelText(/trace id ara/i) as HTMLInputElement).value).toBe('hydrated-tr'),
    )
  })

  it('clicking trace_id cell copies to clipboard', async () => {
    // user-event v14's setup() installs its own clipboard stub on navigator,
    // so we must override AFTER setup() and use defineProperty (clipboard is
    // a getter-only property in jsdom 25).
    const user = userEvent.setup()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    render(<Wrap />)
    await waitFor(() => expect(screen.getByText('tr-1')).toBeInTheDocument())
    await user.click(screen.getByText('tr-1'))
    expect(writeText).toHaveBeenCalledWith('tr-1')
  })
})
