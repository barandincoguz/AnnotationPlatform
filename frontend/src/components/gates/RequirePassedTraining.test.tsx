import { describe, it, expect, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { Routes, Route } from 'react-router-dom'
import { renderWithProviders } from '@/test/render'
import { useAuthStore } from '@/stores/authStore'
import { RequirePassedTraining } from './RequirePassedTraining'

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
      <Route element={<RequirePassedTraining />}>
        <Route path="/" element={<div data-testid="ok">ok</div>} />
      </Route>
      <Route path="/training" element={<div data-testid="route-training">training</div>} />
    </Routes>
  )
}

describe('RequirePassedTraining', () => {
  it('redirects to /training when has_passed_training is false', async () => {
    useAuthStore.getState().setUser({
      ...baseUser,
      has_seen_manual: true,
      has_passed_training: false,
    })
    renderWithProviders(<Tree />, {
      initialEntries: ['/'],
      destinationStubs: [{ path: '/training', testId: 'route-training' }],
    })
    expect(await screen.findByTestId('route-training')).toBeInTheDocument()
  })

  it('renders outlet when has_passed_training is true', () => {
    useAuthStore.getState().setUser({
      ...baseUser,
      has_seen_manual: true,
      has_passed_training: true,
    })
    renderWithProviders(<Tree />, {
      initialEntries: ['/'],
      destinationStubs: [{ path: '/training', testId: 'route-training' }],
    })
    expect(screen.getByTestId('ok')).toBeInTheDocument()
  })
})
