/* eslint-disable react/display-name */
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { server } from '@/test/msw-server'
import { SettingsPage } from './SettingsPage'

const Wrap = () => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <Toaster />
    <SettingsPage />
  </QueryClientProvider>
)

beforeEach(() => {
  server.use(
    http.get('http://localhost/api/admin/settings', () => HttpResponse.json({
      'training.quiz_pass_threshold': 4,
      'gamification.streak_enabled': true,
      'app.name': 'Annotation',
    })),
  )
})

describe('SettingsPage', () => {
  it('renders settings grouped by prefix', async () => {
    render(<Wrap />)
    await waitFor(() => expect(screen.getByText('training.quiz_pass_threshold')).toBeInTheDocument())
    expect(screen.getByText('gamification.streak_enabled')).toBeInTheDocument()
    expect(screen.getByText('app.name')).toBeInTheDocument()
  })

  it('number editor enables Kaydet when changed', async () => {
    const user = userEvent.setup()
    render(<Wrap />)
    await waitFor(() => expect(screen.getByText('training.quiz_pass_threshold')).toBeInTheDocument())
    const input = screen.getByDisplayValue('4') as HTMLInputElement
    await user.clear(input)
    await user.type(input, '5')
    expect(screen.getAllByRole('button', { name: /kaydet/i })[0]).not.toBeDisabled()
  })

  it('boolean editor renders Switch', async () => {
    render(<Wrap />)
    await waitFor(() => expect(screen.getByText('gamification.streak_enabled')).toBeInTheDocument())
    expect(screen.getAllByRole('switch').length).toBeGreaterThan(0)
  })

  it('save mutation invokes PUT and invalidates', async () => {
    let captured: { key?: string; body?: unknown } = {}
    server.use(
      http.put('http://localhost/api/admin/settings/:key', async ({ params, request }) => {
        captured = { key: String(params.key), body: await request.json() }
        return HttpResponse.json({ key: params.key, value: 5 })
      }),
    )
    const user = userEvent.setup()
    render(<Wrap />)
    await waitFor(() => expect(screen.getByText('training.quiz_pass_threshold')).toBeInTheDocument())
    const input = screen.getByDisplayValue('4') as HTMLInputElement
    await user.clear(input)
    await user.type(input, '5')
    const saveBtn = screen.getAllByRole('button', { name: /kaydet/i })[0]
    if (!saveBtn) throw new Error('Kaydet button missing')
    await user.click(saveBtn)
    await waitFor(() => expect(captured.key).toBe('training.quiz_pass_threshold'))
  })
})
