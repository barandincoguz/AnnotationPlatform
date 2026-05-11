import { describe, it, expect, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { Routes, Route } from 'react-router-dom'
import { renderWithProviders } from '@/test/render'
import { useAuthStore } from '@/stores/authStore'
import { RequireAuth } from './RequireAuth'

beforeEach(() => {
  useAuthStore.setState({ status: 'loading', user: null, error: null })
})

function ProtectedTree() {
  return (
    <Routes>
      <Route element={<RequireAuth />}>
        <Route path="/" element={<div data-testid="protected">ok</div>} />
      </Route>
      <Route path="/login" element={<div data-testid="route-login">login</div>} />
    </Routes>
  )
}

describe('RequireAuth', () => {
  it('redirects to /login when anon', async () => {
    useAuthStore.setState({ status: 'anon' })
    renderWithProviders(<ProtectedTree />, {
      initialEntries: ['/'],
      destinationStubs: [{ path: '/login', testId: 'route-login' }],
    })
    expect(await screen.findByTestId('route-login')).toBeInTheDocument()
  })

  it('renders the outlet when authed', () => {
    useAuthStore.getState().setUser({
      id: 1,
      username: 'a',
      email: null,
      role: 'user',
      is_active: true,
      has_seen_manual: true,
      has_passed_training: true,
      avatar_color: null,
      created_at: '2026-05-01T00:00:00+00:00',
    })
    renderWithProviders(<ProtectedTree />, {
      initialEntries: ['/'],
      destinationStubs: [{ path: '/login', testId: 'route-login' }],
    })
    expect(screen.getByTestId('protected')).toBeInTheDocument()
  })
})
