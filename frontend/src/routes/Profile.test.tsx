import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { Profile } from './Profile'
import { useAuthStore } from '@/stores/authStore'
import { makeProfile, defaultBadgesCatalog } from '@/test/msw-handlers'

vi.mock('sonner', () => ({ toast: { success: vi.fn() } }))

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

beforeEach(() => {
  useAuthStore.getState().setUser({
    id: 1, username: 'tester', email: null, role: 'user',
    is_active: true, has_seen_manual: true, has_passed_training: true,
    avatar_color: '#3b82f6', created_at: '2026-05-01T00:00:00+00:00',
  })
})

describe('Profile /me', () => {
  it('renders header + 4 stat cards + badges grid + notifications section', async () => {
    render(<Profile />, { wrapper: wrap() })
    expect(await screen.findByText('@tester')).toBeInTheDocument()
    expect(screen.getByText(/Toplam XP/)).toBeInTheDocument()
    expect(screen.getByText(/Rozetler/)).toBeInTheDocument()
    expect(screen.getByText(/Bildirimler/)).toBeInTheDocument()
  })

  it('fresh user (badges=[]) defaults BadgesGrid to Hepsi tab', async () => {
    server.use(
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json(makeProfile({ badges: [] }))),
      http.get('http://localhost/api/badges/catalog', () =>
        HttpResponse.json(defaultBadgesCatalog())),
    )
    render(<Profile />, { wrapper: wrap() })
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /Hepsi/ })).toHaveAttribute('aria-selected', 'true')
    })
  })

  it('mark-all-read flow: POST fires and button can be clicked', async () => {
    const user = userEvent.setup()
    let posted = false
    server.use(
      http.get('http://localhost/api/me/notifications', () =>
        HttpResponse.json({
          items: [
            { id: 1, kind: 'admin_announcement', title: 'A',
              body: null, data: null, is_read: false,
              created_at: '2026-05-11T00:00:00+00:00' },
          ],
        })),
      http.post('http://localhost/api/me/notifications/read-all', () => {
        posted = true
        return HttpResponse.json({ marked_count: 1 })
      }),
    )
    render(<Profile />, { wrapper: wrap() })
    await user.click(await screen.findByText(/Tümünü okundu yap/))
    await waitFor(() => expect(posted).toBe(true))
  })

  it('on profile fetch error shows a full-page retry block', async () => {
    server.use(
      http.get('http://localhost/api/me/profile', () =>
        HttpResponse.json({ broken: true }, { status: 500 })),
    )
    render(<Profile />, { wrapper: wrap() })
    expect(await screen.findByText(/Profil yüklenemedi/i)).toBeInTheDocument()
  })
})
