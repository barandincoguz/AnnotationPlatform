import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, render } from '@testing-library/react'
import { Route, Routes, MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppShell } from './AppShell'
import { useAuthStore } from '@/stores/authStore'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }))

function renderAppShell() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<div data-testid="child">child</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  useAuthStore.getState().setUser({
    id: 1, username: 'tester', email: null, role: 'user',
    is_active: true, has_seen_manual: true, has_passed_training: true,
    avatar_color: '#3b82f6', created_at: '2026-05-01T00:00:00+00:00',
  })
})

describe('AppShell', () => {
  it('renders the outlet so nested routes display below the TopBar', () => {
    renderAppShell()
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })

  it('mounts the TopBar (role=banner)', () => {
    renderAppShell()
    expect(screen.getByRole('banner')).toBeInTheDocument()
  })
})
