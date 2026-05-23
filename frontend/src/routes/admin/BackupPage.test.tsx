import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BackupPage } from './BackupPage'

function renderWithProviders(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('BackupPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.url
      const method = init?.method ?? 'GET'
      if (url.includes('/api/admin/system-events') && method === 'GET') {
        return new Response(JSON.stringify({
          items: [
            {
              id: 1,
              event_type: 'backup_success',
              severity: 'info',
              message: 'snapshot pushed',
              extra: '{}',
              created_at: '2026-05-23T10:00:00Z',
            },
          ],
          total: 1,
          has_more: false,
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      if (url.endsWith('/api/admin/backup/run-now') && method === 'POST') {
        return new Response(JSON.stringify({
          ok: true,
          snapshot_path: '/data/x.json',
          committed_sha: 'abc1234567',
          pushed: true,
          rotated_count: 0,
          trace_id: 't-1',
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      throw new Error(`unexpected fetch: ${url}`)
    }))
  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('renders history list', async () => {
    renderWithProviders(<BackupPage />)
    await waitFor(() => expect(screen.getByText(/snapshot pushed/)).toBeInTheDocument())
    expect(screen.getByText(/backup_success/)).toBeInTheDocument()
  })

  it('clicking Şimdi yedek al fires the backup and toasts success', async () => {
    const { toast } = await import('sonner')
    const spy = vi.spyOn(toast, 'success')
    renderWithProviders(<BackupPage />)
    await waitFor(() => screen.getByText(/Şimdi yedek al/))
    fireEvent.click(screen.getByText(/Şimdi yedek al/))
    await waitFor(() => expect(spy).toHaveBeenCalledWith('Yedek alındı'))
  })

  it('shows committed_sha snippet after a successful run', async () => {
    renderWithProviders(<BackupPage />)
    fireEvent.click(await screen.findByText(/Şimdi yedek al/))
    await waitFor(() => expect(screen.getByText(/sha: abc1234/)).toBeInTheDocument())
  })
})
