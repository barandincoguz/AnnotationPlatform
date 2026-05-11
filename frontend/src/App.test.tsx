import { describe, it, expect, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { server } from '@/test/msw-server'
import { http, HttpResponse } from 'msw'
import { mockAuthedUser, mockAnonUser, makeUser } from '@/test/msw-handlers'
import { useAuthStore } from '@/stores/authStore'
import { renderWithProviders } from '@/test/render'
import App from './App'

beforeEach(() => useAuthStore.setState({ status: 'loading', user: null, error: null }))

describe('App hydration', () => {
  it('starts in loading, transitions to authed, renders root', async () => {
    server.use(mockAuthedUser({ username: 'bob' }))
    renderWithProviders(<App />, { initialEntries: ['/'], wildcardEntry: true })
    expect(screen.getByText('Yükleniyor…')).toBeInTheDocument()
    await waitFor(() => expect(useAuthStore.getState().status).toBe('authed'))
    await waitFor(() => expect(screen.getByTestId('stub-annotate')).toBeInTheDocument())
  })

  it('starts in loading, transitions to anon on 401, redirects /login', async () => {
    server.use(mockAnonUser())
    renderWithProviders(<App />, { initialEntries: ['/'], wildcardEntry: true })
    await waitFor(() => expect(useAuthStore.getState().status).toBe('anon'))
    // RequireAuth redirects to /login; the Login form should render
    await waitFor(() => expect(screen.getByRole('button', { name: /giriş yap/i })).toBeInTheDocument())
  })

  it('on network error: shows error mode + retry button works', async () => {
    let callCount = 0
    server.use(
      http.get('http://localhost/api/auth/me', () => {
        callCount += 1
        if (callCount === 1) {
          return HttpResponse.error()
        }
        return HttpResponse.json(makeUser({ username: 'recovered' }))
      }),
    )
    renderWithProviders(<App />, { initialEntries: ['/'], wildcardEntry: true })
    await waitFor(() =>
      expect(screen.getByText(/Sunucuya bağlanılamadı/i)).toBeInTheDocument(),
    )

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /tekrar dene/i }))
    await waitFor(() => expect(useAuthStore.getState().status).toBe('authed'))
    expect(callCount).toBe(2)
  })
})
