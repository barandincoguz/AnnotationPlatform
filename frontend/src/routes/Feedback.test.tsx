import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { renderWithProviders } from '@/test/render'
import { Feedback } from './Feedback'

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

describe('Feedback', () => {
  it('renders the feedback form', () => {
    renderWithProviders(<Feedback />, { initialEntries: ['/feedback'] })

    expect(screen.getByRole('heading', { name: /geri bildirim/i })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /öneri/i })).toBeChecked()
    expect(screen.getByRole('radio', { name: /şikayet/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/mesaj/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /gönder/i })).toBeDisabled()
  })

  it('submits trimmed feedback payload', async () => {
    const user = userEvent.setup()
    let captured: unknown
    server.use(
      http.post('http://localhost/api/feedback', async ({ request }) => {
        captured = await request.json()
        return HttpResponse.json({
          id: 10,
          user_id: 1,
          username: 'tester',
          type: 'complaint',
          message: 'Panel kapanıyor',
          created_at: '2026-07-07T12:00:00+00:00',
        }, { status: 201 })
      }),
    )

    renderWithProviders(<Feedback />, { initialEntries: ['/feedback'] })

    await user.click(screen.getByRole('radio', { name: /şikayet/i }))
    await user.type(screen.getByLabelText(/mesaj/i), '  Panel kapanıyor  ')
    await user.click(screen.getByRole('button', { name: /gönder/i }))

    await waitFor(() =>
      expect(captured).toEqual({ type: 'complaint', message: 'Panel kapanıyor' }),
    )
    expect(await screen.findByRole('status')).toHaveTextContent(/kaydedildi/i)
    expect(screen.getByLabelText<HTMLTextAreaElement>(/mesaj/i).value).toBe('')
  })
})

