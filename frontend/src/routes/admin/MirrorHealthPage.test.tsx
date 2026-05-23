import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MirrorHealthPage } from './MirrorHealthPage'

function renderWithProviders(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('MirrorHealthPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo) => {
      const url = typeof input === 'string' ? input : input.url
      if (url.endsWith('/api/admin/mirror/health')) {
        return new Response(JSON.stringify({
          queue_depth: 42,
          dead_letter_count: 0,
          oldest_undelivered_age_seconds: 12.4,
          last_delivered_at: '2026-05-23T15:00:00Z',
          dispatcher_alive: true,
          neon_reachable: true,
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      throw new Error(`unexpected fetch: ${url}`)
    }))
  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('renders queue depth and dispatcher alive', async () => {
    renderWithProviders(<MirrorHealthPage />)
    await waitFor(() => expect(screen.getByText(/42/)).toBeInTheDocument())
    expect(screen.getByText(/dispatcher alive/i)).toBeInTheDocument()
  })

  it('applies warn class when queue depth crosses 1000', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      queue_depth: 1500, dead_letter_count: 0,
      oldest_undelivered_age_seconds: 100, last_delivered_at: null,
      dispatcher_alive: true, neon_reachable: true,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

    renderWithProviders(<MirrorHealthPage />)
    await waitFor(() => {
      const el = screen.getByTestId('queue-depth')
      expect(el.className).toMatch(/amber/)
    })
  })

  it('applies critical class when queue depth crosses 10000', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      queue_depth: 20000, dead_letter_count: 0,
      oldest_undelivered_age_seconds: 1000, last_delivered_at: null,
      dispatcher_alive: true, neon_reachable: false,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

    renderWithProviders(<MirrorHealthPage />)
    await waitFor(() => {
      const el = screen.getByTestId('queue-depth')
      expect(el.className).toMatch(/destructive/)
    })
  })

  it('renders neon-reachable false', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      queue_depth: 0, dead_letter_count: 0,
      oldest_undelivered_age_seconds: null, last_delivered_at: null,
      dispatcher_alive: true, neon_reachable: false,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

    renderWithProviders(<MirrorHealthPage />)
    await waitFor(() => expect(screen.getByText(/^hayır$/)).toBeInTheDocument())
  })
})
