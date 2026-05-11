import { describe, it, expect } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/msw-server'
import { http, HttpResponse } from 'msw'
import { useAuthStore } from '@/stores/authStore'
import { Register } from './Register'

describe('Register route', () => {
  it('on success: navigates to /login (does NOT auth)', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Register />, { initialEntries: ['/register'] })
    await user.type(screen.getByLabelText(/kullanıcı adı/i), 'newone')
    await user.type(screen.getByLabelText(/şifre/i), 'StrongPw1!')
    await user.type(screen.getByLabelText(/davet kodu/i), 'XYZ')
    await user.click(screen.getByRole('button', { name: /kayıt ol/i }))
    await waitFor(() =>
      expect(screen.getByTestId('route-login')).toBeInTheDocument(),
    )
    expect(useAuthStore.getState().status).not.toBe('authed')
  })

  it('on 409 username taken: shows error', async () => {
    server.use(
      http.post('http://localhost/api/auth/register', () =>
        HttpResponse.json(
          { detail: "username 'newone' already taken" },
          { status: 409 },
        ),
      ),
    )
    const user = userEvent.setup()
    renderWithProviders(<Register />, { initialEntries: ['/register'] })
    await user.type(screen.getByLabelText(/kullanıcı adı/i), 'newone')
    await user.type(screen.getByLabelText(/şifre/i), 'StrongPw1!')
    await user.type(screen.getByLabelText(/davet kodu/i), 'XYZ')
    await user.click(screen.getByRole('button', { name: /kayıt ol/i }))
    await waitFor(() =>
      expect(screen.getByText(/already taken/i)).toBeInTheDocument(),
    )
  })

  it('on 403 invalid invite: shows error', async () => {
    server.use(
      http.post('http://localhost/api/auth/register', () =>
        HttpResponse.json({ detail: 'invalid invite code' }, { status: 403 }),
      ),
    )
    const user = userEvent.setup()
    renderWithProviders(<Register />, { initialEntries: ['/register'] })
    await user.type(screen.getByLabelText(/kullanıcı adı/i), 'newone')
    await user.type(screen.getByLabelText(/şifre/i), 'StrongPw1!')
    await user.type(screen.getByLabelText(/davet kodu/i), 'WRONG')
    await user.click(screen.getByRole('button', { name: /kayıt ol/i }))
    await waitFor(() =>
      expect(screen.getByText(/invalid invite/i)).toBeInTheDocument(),
    )
  })
})
