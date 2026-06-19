import { describe, it, expect, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { Routes, Route } from 'react-router-dom'
import { renderWithProviders } from '@/test/render'
import { useAuthStore } from '@/stores/authStore'
import { RequireSeenManual } from './RequireSeenManual'

const baseUser = {
  id: 1,
  username: 'u',
  email: null,
  role: 'user' as const,
  is_active: true,
  avatar_color: null,
  created_at: '2026-05-01T00:00:00+00:00',
}

beforeEach(() => useAuthStore.setState({ status: 'loading', user: null, error: null }))

function Tree() {
  return (
    <Routes>
      <Route element={<RequireSeenManual />}>
        <Route path="/" element={<div data-testid="ok">ok</div>} />
      </Route>
      <Route path="/help" element={<div data-testid="route-help">help</div>} />
    </Routes>
  )
}

describe('RequireSeenManual', () => {
  it('redirects to /help?first_time=true when has_seen_manual is false', async () => {
    useAuthStore.getState().setUser({
      ...baseUser,
      has_seen_manual: false,
      has_passed_training: true,
    })
    renderWithProviders(<Tree />, {
      initialEntries: ['/'],
      wildcardEntry: true,
    })
    expect(await screen.findByTestId('route-help')).toBeInTheDocument()
  })

  it('renders outlet when has_seen_manual is true', () => {
    useAuthStore.getState().setUser({
      ...baseUser,
      has_seen_manual: true,
      has_passed_training: true,
    })
    renderWithProviders(<Tree />, {
      initialEntries: ['/'],
      wildcardEntry: true,
    })
    expect(screen.getByTestId('ok')).toBeInTheDocument()
  })
})
