import { describe, it, expect } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { mockAuthedUser } from '@/test/msw-handlers'
import { server } from '@/test/msw-server'
import { renderWithProviders } from '@/test/render'
import { Help } from './Help'
import { useAuthStore } from '@/stores/authStore'

const API = 'http://localhost'

describe('Help route', () => {
  it('renders accordion in normal mode without CTA', async () => {
    server.use(mockAuthedUser({ has_seen_manual: true, has_passed_training: false }))
    renderWithProviders(<Help />, { initialEntries: ['/help'] })
    await waitFor(() => expect(screen.getByRole('button', { name: /hoş geldin/i })).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /eğitime geç/i })).not.toBeInTheDocument()
  })

  it('renders banner + CTA in first_time mode', async () => {
    server.use(mockAuthedUser({ has_seen_manual: false, has_passed_training: false }))
    renderWithProviders(<Help />, { initialEntries: ['/help?first_time=true'] })
    await waitFor(() => expect(screen.getByRole('button', { name: /eğitime geç/i })).toBeInTheDocument())
    expect(screen.getByText(/lütfen başlamadan önce/i)).toBeInTheDocument()
  })

  it('CTA click POSTs seen-manual, refreshes auth, and navigates to /training', async () => {
    const user = userEvent.setup()
    let seenManualCalled = false
    server.use(
      mockAuthedUser({ has_seen_manual: false }),
      http.post(`${API}/api/me/seen-manual`, () => {
        seenManualCalled = true
        return HttpResponse.json({ ok: true })
      }),
    )
    useAuthStore.setState({
      status: 'authed',
      user: { id: 1, username: 't', role: 'user', avatar_color: '#000', has_seen_manual: false, has_passed_training: false } as never,
      error: null,
    })

    renderWithProviders(<Help />, { initialEntries: ['/help?first_time=true'] })
    await waitFor(() => expect(screen.getByRole('button', { name: /eğitime geç/i })).toBeInTheDocument())

    server.use(mockAuthedUser({ has_seen_manual: true }))
    await user.click(screen.getByRole('button', { name: /eğitime geç/i }))

    await waitFor(() => expect(seenManualCalled).toBe(true))
    await waitFor(() => expect(screen.getByTestId('route-training')).toBeInTheDocument())
  })

  it('CTA error keeps user on page (button re-enabled)', async () => {
    const user = userEvent.setup()
    server.use(
      mockAuthedUser({ has_seen_manual: false }),
      http.post(`${API}/api/me/seen-manual`, () =>
        HttpResponse.json({ detail: { error: 'boom', message: 'sunucu hatası' } }, { status: 500 }),
      ),
    )
    renderWithProviders(<Help />, { initialEntries: ['/help?first_time=true'] })
    await waitFor(() => expect(screen.getByRole('button', { name: /eğitime geç/i })).toBeInTheDocument())
    const cta = screen.getByRole('button', { name: /eğitime geç/i })
    await user.click(cta)
    await waitFor(() => expect(cta).not.toBeDisabled())
  })

  it('error path for help fetch renders error message', async () => {
    server.use(
      mockAuthedUser({ has_seen_manual: true }),
      http.get(`${API}/api/help`, () => HttpResponse.error()),
    )
    renderWithProviders(<Help />, { initialEntries: ['/help'] })
    await waitFor(() =>
      expect(screen.getAllByText(/yardım yüklenemedi|tekrar dene/i).length).toBeGreaterThan(0),
    )
  })
})
