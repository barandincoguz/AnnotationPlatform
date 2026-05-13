/* eslint-disable react/display-name */
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { server } from '@/test/msw-server'
import { EventsPage } from './EventsPage'

const Wrap = ({ search = '' }: { search?: string }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[`/admin/events${search}`]}>
      <EventsPage />
    </MemoryRouter>
  </QueryClientProvider>
)

beforeEach(() => {
  server.use(
    http.get('http://localhost/api/admin/system-events', () =>
      HttpResponse.json({
        items: [{
          id: 1, event_type: 'training_skipped', severity: 'info',
          message: 'skip', extra: null, trace_id: null,
          created_at: '2026-05-12T10:00:00+00:00',
        }],
        total: 1, has_more: false,
      }),
    ),
  )
})

describe('EventsPage', () => {
  it('renders a row', async () => {
    render(<Wrap />)
    await waitFor(() => expect(screen.getByText('training_skipped')).toBeInTheDocument())
    expect(screen.getByText('info')).toBeInTheDocument()
  })

  it('event_type filter is URL-synced', async () => {
    render(<Wrap search="?event_type=training_pass" />)
    await waitFor(() =>
      expect((screen.getByLabelText(/event type/i) as HTMLInputElement).value).toBe('training_pass'),
    )
  })
})
