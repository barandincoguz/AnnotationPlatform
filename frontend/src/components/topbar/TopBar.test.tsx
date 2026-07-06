/* eslint-disable react/display-name -- test wrappers, no display name needed */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { TopBar } from './TopBar'
import { useAuthStore } from '@/stores/authStore'
import { makeProfile } from '@/test/msw-handlers'

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

function wrap() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        {children}
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  useAuthStore.getState().setUser({
    id: 1, username: 'tester', email: null, role: 'user',
    is_active: true, has_seen_manual: true, has_passed_training: true,
    avatar_color: '#3b82f6', created_at: '2026-05-01T00:00:00+00:00',
  })
})

describe('TopBar', () => {
  it('renders logo + project name', () => {
    render(<TopBar />, { wrapper: wrap() })
    expect(screen.getByText('Anotasyon Platformu')).toBeInTheDocument()
  })

  it('renders XP from useProfile', async () => {
    server.use(
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json(makeProfile({ xp: { total: 1240 } }))),
    )
    render(<TopBar />, { wrapper: wrap() })
    await waitFor(() => expect(screen.getByLabelText('Toplam XP')).toHaveTextContent('1.240'))
  })

  it('renders the statistics link immediately before the XP badge', () => {
    render(<TopBar />, { wrapper: wrap() })
    const center = screen.getByTestId('topbar-center')
    const statsLink = within(center).getByRole('link', { name: 'İstatistikler' })
    const xpBadge = within(center).getByLabelText('Toplam XP')

    expect(statsLink).toHaveAttribute('href', '/statistics')
    expect(Boolean(statsLink.compareDocumentPosition(xpBadge) & Node.DOCUMENT_POSITION_FOLLOWING))
      .toBe(true)
  })

  it('on profile error, stats show fallback but TopBar does not crash', async () => {
    server.use(
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json({ broken: true }, { status: 500 })),
    )
    render(<TopBar />, { wrapper: wrap() })
    await waitFor(() => {
      expect(screen.getByLabelText(/streak/i)).toHaveTextContent('—')
    })
    expect(screen.getByText('Anotasyon Platformu')).toBeInTheDocument()
  })

  it('hides OnlineUsers when fetch errors', async () => {
    server.use(
      http.get('http://localhost/api/users/online', () =>
        HttpResponse.json({ broken: true }, { status: 500 })),
    )
    render(<TopBar />, { wrapper: wrap() })
    await waitFor(() => {
      expect(screen.queryByLabelText(/kullanıcı çevrimiçi/)).not.toBeInTheDocument()
    })
  })
})
