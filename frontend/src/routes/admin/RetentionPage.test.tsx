import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { RetentionPage } from './RetentionPage'

function renderWithProviders(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      {ui}
      <Toaster />
    </QueryClientProvider>
  )
}

const PREVIEW_OK = {
  rows_to_purge: { admin_audit_log: 12, system_events: 5 },
  total: 17,
  policy: [
    { table: 'admin_audit_log', days: 90, cutoff_iso: '2026-02-22T00:00:00Z' },
    { table: 'system_events', days: 30, cutoff_iso: '2026-04-23T00:00:00Z' },
  ],
}

const RUN_NOW_OK = {
  ok: true,
  total: 17,
  purged: { admin_audit_log: 12, system_events: 5 },
  trace_id: 't-1',
}

describe('RetentionPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.url
      const method = init?.method ?? 'GET'
      if (url.endsWith('/api/admin/retention/preview') && method === 'GET') {
        return new Response(JSON.stringify(PREVIEW_OK), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (url.endsWith('/api/admin/retention/run-now') && method === 'POST') {
        return new Response(JSON.stringify(RUN_NOW_OK), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      throw new Error(`unexpected fetch: ${url}`)
    }))
  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('shows preview totals + per-table breakdown', async () => {
    renderWithProviders(<RetentionPage />)
    await waitFor(() => expect(screen.getByTestId('retention-total')).toHaveTextContent('17'))
    expect(screen.getAllByText(/admin_audit_log/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/system_events/).length).toBeGreaterThan(0)
  })

  it('Şimdi temizle opens confirm modal; Vazgeç closes it', async () => {
    renderWithProviders(<RetentionPage />)
    // Wait until data is loaded (button becomes enabled)
    await waitFor(() => {
      const btn = screen.getByText(/Şimdi temizle/)
      expect(btn).not.toBeDisabled()
    })
    fireEvent.click(screen.getByText(/Şimdi temizle/))
    await waitFor(() =>
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    )
    fireEvent.click(screen.getByText(/Vazgeç/))
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    )
  })

  it('Confirm fires retention/run-now and toasts the total', async () => {
    renderWithProviders(<RetentionPage />)
    // Wait until button is enabled (data loaded)
    const btn = await screen.findByText(/Şimdi temizle/)
    await waitFor(() => expect(btn).not.toBeDisabled())
    fireEvent.click(btn)
    fireEvent.click(await screen.findByText(/Evet, sil/))
    await waitFor(() =>
      expect(screen.getByText(/17 satır silindi/)).toBeInTheDocument()
    )
  })

  it('Şimdi temizle disabled when total is 0', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ rows_to_purge: {}, total: 0, policy: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    ))
    renderWithProviders(<RetentionPage />)
    await waitFor(() => expect(screen.getByTestId('retention-total')).toHaveTextContent('0'))
    expect(screen.getByText(/Şimdi temizle/)).toBeDisabled()
  })
})
