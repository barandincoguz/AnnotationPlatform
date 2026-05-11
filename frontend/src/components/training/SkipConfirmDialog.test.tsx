/* eslint-disable react/display-name -- test wrappers, no display name needed */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { SkipConfirmDialog } from './SkipConfirmDialog'

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

function wrap() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('SkipConfirmDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders title + body + input + buttons when open', () => {
    render(
      <SkipConfirmDialog open={true} onClose={vi.fn()} />,
      { wrapper: wrap() },
    )
    expect(screen.getByText(/asla önerilmez/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText('SKIP')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Vazgeç/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Eğitimi Atla/ })).toBeInTheDocument()
  })

  it('"Eğitimi Atla" is disabled until user types exactly "SKIP"', async () => {
    const user = userEvent.setup()
    render(
      <SkipConfirmDialog open={true} onClose={vi.fn()} />,
      { wrapper: wrap() },
    )
    const submit = screen.getByRole('button', { name: /Eğitimi Atla/ })
    expect(submit).toBeDisabled()

    const input = screen.getByPlaceholderText('SKIP')
    await user.type(input, 'skip')  // lowercase
    expect(submit).toBeDisabled()

    await user.clear(input)
    await user.type(input, 'SKIP')
    expect(submit).not.toBeDisabled()
  })

  it('"Vazgeç" calls onClose', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(
      <SkipConfirmDialog open={true} onClose={onClose} />,
      { wrapper: wrap() },
    )
    await user.click(screen.getByRole('button', { name: /Vazgeç/ }))
    expect(onClose).toHaveBeenCalled()
  })

  it('clicking "Eğitimi Atla" with valid input fires the skip mutation', async () => {
    let posted = false
    server.use(
      http.post('http://localhost/api/training/skip', () => {
        posted = true
        return HttpResponse.json({ ok: true })
      }),
      http.get('http://localhost/api/auth/me', () =>
        HttpResponse.json({
          id: 1, username: 'tester', email: null, role: 'user',
          is_active: true, has_seen_manual: true, has_passed_training: true,
          avatar_color: '#3b82f6', created_at: '2026-05-01T00:00:00+00:00',
        })),
    )
    const user = userEvent.setup()
    render(
      <SkipConfirmDialog open={true} onClose={vi.fn()} />,
      { wrapper: wrap() },
    )
    await user.type(screen.getByPlaceholderText('SKIP'), 'SKIP')
    await user.click(screen.getByRole('button', { name: /Eğitimi Atla/ }))
    await waitFor(() => expect(posted).toBe(true))
  })
})
