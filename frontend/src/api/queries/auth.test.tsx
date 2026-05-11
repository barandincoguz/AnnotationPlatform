import { describe, it, expect, beforeEach, vi } from 'vitest'
import { act, waitFor, screen } from '@testing-library/react'
import { renderWithProviders } from '@/test/render'
import { useAuthStore } from '@/stores/authStore'
import { server } from '@/test/msw-server'
import { mockAuthedUser, makeUser } from '@/test/msw-handlers'
import { http, HttpResponse } from 'msw'
import type { ApiError } from '@/api/client'
import { useMe, useLoginMutation, useRegisterMutation, useLogoutMutation } from './auth'

beforeEach(() => {
  useAuthStore.setState({ status: 'loading', user: null, error: null })
})

describe('useMe', () => {
  it('returns user data when authed status', async () => {
    server.use(mockAuthedUser({ username: 'alice' }))
    useAuthStore.setState({ status: 'authed' }) // enabled gate
    function Probe() {
      const q = useMe()
      return <div data-testid="result">{q.data?.username ?? 'pending'}</div>
    }
    renderWithProviders(<Probe />)
    await waitFor(() => expect(screen.getByTestId('result').textContent).toBe('alice'))
  })

  it('is disabled when status is anon', () => {
    useAuthStore.setState({ status: 'anon' })
    function Probe() {
      const q = useMe()
      return <div data-testid="state">{q.isPending && !q.isFetching ? 'idle' : 'active'}</div>
    }
    renderWithProviders(<Probe />)
    expect(screen.getByTestId('state').textContent).toBe('idle')
  })
})

describe('useRegisterMutation', () => {
  it('on success: shows toast and navigates to /login (NOT authed)', async () => {
    const Toaster = await import('sonner')
    const toastSpy = vi.spyOn(Toaster.toast, 'success')

    function Probe() {
      const m = useRegisterMutation()
      return (
        <button
          data-testid="trigger"
          onClick={() => m.mutate({ username: 'new', password: 'Strong1!', invite_code: 'XYZ' })}
        >
          go
        </button>
      )
    }
    renderWithProviders(<Probe />, { initialEntries: ['/register'] })
    act(() => screen.getByTestId('trigger').click())
    await waitFor(() => expect(screen.getByTestId('route-login')).toBeInTheDocument())
    expect(toastSpy).toHaveBeenCalled()
    // authStore must NOT be seeded — backend register did not set a session
    expect(useAuthStore.getState().status).not.toBe('authed')
  })
})

describe('useLogoutMutation', () => {
  it('clears authStore, clears queries, navigates to /login', async () => {
    useAuthStore.getState().setUser(makeUser())
    function Probe() {
      const m = useLogoutMutation()
      return (
        <button data-testid="trigger" onClick={() => m.mutate()}>
          go
        </button>
      )
    }
    renderWithProviders(<Probe />, { initialEntries: ['/'] })
    act(() => screen.getByTestId('trigger').click())
    await waitFor(() => expect(useAuthStore.getState().status).toBe('anon'))
    await waitFor(() => expect(screen.getByTestId('route-login')).toBeInTheDocument())
  })
})

describe('useLoginMutation', () => {
  it('on success: makes a follow-up /me call, seeds authStore', async () => {
    server.use(
      http.post('http://localhost/api/auth/login', () => HttpResponse.json({ ok: true })),
      mockAuthedUser({ username: 'bob' }),
    )
    function Probe() {
      const m = useLoginMutation()
      return (
        <button data-testid="trigger" onClick={() => m.mutate({ username: 'bob', password: 'pw' })}>
          go
        </button>
      )
    }
    renderWithProviders(<Probe />, { initialEntries: ['/login'] })
    act(() => screen.getByTestId('trigger').click())
    await waitFor(() => expect(useAuthStore.getState().status).toBe('authed'))
    expect(useAuthStore.getState().user?.username).toBe('bob')
  })

  it('on failure: surfaces ApiError, does NOT seed authStore', async () => {
    server.use(
      http.post('http://localhost/api/auth/login', () =>
        HttpResponse.json(
          { detail: { error: 'invalid_credentials', message: 'Şifre hatalı' } },
          { status: 401 },
        ),
      ),
    )
    function Probe() {
      const m = useLoginMutation()
      return (
        <>
          <button data-testid="trigger" onClick={() => m.mutate({ username: 'x', password: 'y' })}>
            go
          </button>
          <div data-testid="state">{m.isError ? `err:${(m.error as ApiError).code}` : '...'}</div>
        </>
      )
    }
    renderWithProviders(<Probe />, { initialEntries: ['/login'] })
    act(() => screen.getByTestId('trigger').click())
    await waitFor(() =>
      expect(screen.getByTestId('state').textContent).toBe('err:invalid_credentials'),
    )
    expect(useAuthStore.getState().status).not.toBe('authed')
  })
})
