import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { type ReactNode } from 'react'
import { useAuth } from './useAuth'
import { useAuthStore } from '@/stores/authStore'

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient()}>
    <MemoryRouter>{children}</MemoryRouter>
  </QueryClientProvider>
)

beforeEach(() => useAuthStore.setState({ status: 'loading', user: null, error: null }))

describe('useAuth', () => {
  it('exposes status, user, isAuthed, isAdmin', () => {
    useAuthStore.getState().setUser({
      id: 1, username: 'a', email: null, role: 'admin',
      is_active: true, has_seen_manual: true, has_passed_training: true,
      avatar_color: null, created_at: '2026-05-01T00:00:00+00:00',
    })
    const { result } = renderHook(() => useAuth(), { wrapper })
    expect(result.current.status).toBe('authed')
    expect(result.current.user?.username).toBe('a')
    expect(result.current.isAuthed).toBe(true)
    expect(result.current.isAdmin).toBe(true)
  })

  it('exposes loginMutation, registerMutation, logoutMutation', () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    expect(typeof result.current.loginMutation.mutate).toBe('function')
    expect(typeof result.current.registerMutation.mutate).toBe('function')
    expect(typeof result.current.logoutMutation.mutate).toBe('function')
  })
})
