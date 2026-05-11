import { describe, it, expect, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '@/test/render'
import { useAuthStore } from '@/stores/authStore'
import { RequireAdmin } from './RequireAdmin'

const baseUser = {
  id: 1,
  username: 'u',
  email: null,
  is_active: true,
  has_seen_manual: true,
  has_passed_training: true,
  avatar_color: null,
  created_at: '2026-05-01T00:00:00+00:00',
}

beforeEach(() => useAuthStore.setState({ status: 'loading', user: null, error: null }))

describe('RequireAdmin', () => {
  it('renders 404 fallback when user is not admin (existence-hide)', () => {
    useAuthStore.getState().setUser({ ...baseUser, role: 'user' })
    renderWithProviders(
      <RequireAdmin>
        <div data-testid="admin-page">admin</div>
      </RequireAdmin>,
    )
    expect(screen.queryByTestId('admin-page')).toBeNull()
    expect(screen.getByText(/sayfa bulunamadı/i)).toBeInTheDocument()
  })

  it('renders children when user is admin', () => {
    useAuthStore.getState().setUser({ ...baseUser, role: 'admin' })
    renderWithProviders(
      <RequireAdmin>
        <div data-testid="admin-page">admin</div>
      </RequireAdmin>,
    )
    expect(screen.getByTestId('admin-page')).toBeInTheDocument()
  })
})
