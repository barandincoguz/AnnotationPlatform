import { describe, it, expect } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/msw-server'
import { http, HttpResponse } from 'msw'
import { mockAuthedUser } from '@/test/msw-handlers'
import { useAuthStore } from '@/stores/authStore'
import { Login } from './Login'

describe('Login route', () => {
  it('on submit success: authed + navigates to /', async () => {
    server.use(
      http.post('http://localhost/api/auth/login', () => HttpResponse.json({ ok: true })),
      mockAuthedUser({ username: 'baran' }),
    )
    const user = userEvent.setup()
    renderWithProviders(<Login />, { initialEntries: ['/login'] })
    await user.type(screen.getByLabelText(/kullanıcı adı/i), 'baran')
    await user.type(screen.getByLabelText(/şifre/i), 'pw123456')
    await user.click(screen.getByRole('button', { name: /giriş yap/i }))
    await waitFor(() => expect(useAuthStore.getState().status).toBe('authed'))
    await waitFor(() => expect(screen.getByTestId('route-root')).toBeInTheDocument())
  })

  it('on invalid credentials: shows error, stays on form', async () => {
    server.use(
      http.post('http://localhost/api/auth/login', () =>
        HttpResponse.json(
          { detail: { error: 'invalid_credentials', message: 'Şifre hatalı' } },
          { status: 401 },
        ),
      ),
    )
    const user = userEvent.setup()
    renderWithProviders(<Login />, { initialEntries: ['/login'] })
    await user.type(screen.getByLabelText(/kullanıcı adı/i), 'baran')
    await user.type(screen.getByLabelText(/şifre/i), 'wrongpw')
    await user.click(screen.getByRole('button', { name: /giriş yap/i }))
    await waitFor(() => expect(screen.getByText(/şifre hatalı/i)).toBeInTheDocument())
    expect(useAuthStore.getState().status).not.toBe('authed')
  })

  it('submit button is disabled when fields are empty (form-level validation)', () => {
    renderWithProviders(<Login />, { initialEntries: ['/login'] })
    expect(screen.getByRole('button', { name: /giriş yap/i })).toBeDisabled()
  })
})
