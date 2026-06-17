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
    await waitFor(() => expect(screen.getByTestId('route-login')).toBeInTheDocument())
    expect(useAuthStore.getState().status).not.toBe('authed')
  })

  it('trims username and normalizes invite code before submitting', async () => {
    let submittedBody: { username?: string; invite_code?: string } = {}
    server.use(
      http.post('http://localhost/api/auth/register', async ({ request }) => {
        submittedBody = await request.json() as { username: string; invite_code: string }
        return HttpResponse.json({
          id: 2,
          username: 'newone',
          email: null,
          role: 'user',
          is_active: true,
          has_seen_manual: false,
          has_passed_training: false,
          avatar_color: '#3b82f6',
          created_at: '2026-06-17T00:00:00+00:00',
        }, { status: 201 })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<Register />, { initialEntries: ['/register'] })
    await user.type(screen.getByLabelText(/kullanıcı adı/i), '  newone  ')
    await user.type(screen.getByLabelText(/şifre/i), 'StrongPw1!')
    await user.type(screen.getByLabelText(/davet kodu/i), '  demo-2026  ')
    await user.click(screen.getByRole('button', { name: /kayıt ol/i }))
    await waitFor(() => {
      expect(submittedBody).toMatchObject({
        username: 'newone',
        invite_code: 'DEMO-2026',
      })
    })
  })

  it('on 409 username taken: shows error', async () => {
    server.use(
      http.post('http://localhost/api/auth/register', () =>
        HttpResponse.json({ detail: "username 'newone' already taken" }, { status: 409 }),
      ),
    )
    const user = userEvent.setup()
    renderWithProviders(<Register />, { initialEntries: ['/register'] })
    await user.type(screen.getByLabelText(/kullanıcı adı/i), 'newone')
    await user.type(screen.getByLabelText(/şifre/i), 'StrongPw1!')
    await user.type(screen.getByLabelText(/davet kodu/i), 'XYZ')
    await user.click(screen.getByRole('button', { name: /kayıt ol/i }))
    await waitFor(() => expect(screen.getByText(/already taken/i)).toBeInTheDocument())
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
    await waitFor(() => expect(screen.getByText(/invalid invite/i)).toBeInTheDocument())
  })

  it('shows link to login page that navigates on click', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Register />, { initialEntries: ['/register'] })
    const link = screen.getByRole('link', { name: /giriş yap/i })
    expect(link).toHaveAttribute('href', '/login')
    await user.click(link)
    await waitFor(() => expect(screen.getByTestId('route-login')).toBeInTheDocument())
  })

  it('submit button stays disabled for whitespace-only username and invite code', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Register />, { initialEntries: ['/register'] })
    await user.type(screen.getByLabelText(/kullanıcı adı/i), '   ')
    await user.type(screen.getByLabelText(/şifre/i), 'StrongPw1!')
    await user.type(screen.getByLabelText(/davet kodu/i), '   ')
    expect(screen.getByRole('button', { name: /kayıt ol/i })).toBeDisabled()
  })
})
