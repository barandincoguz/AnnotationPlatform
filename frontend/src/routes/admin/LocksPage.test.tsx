/* eslint-disable react/display-name */
import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { server } from '@/test/msw-server'
import { LocksPage } from './LocksPage'

const Wrap = () => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <Toaster />
    <LocksPage />
  </QueryClientProvider>
)

describe('LocksPage', () => {
  it('renders input + Kilidi Aç button', () => {
    render(<Wrap />)
    expect(screen.getByLabelText(/document id/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /kilidi aç/i })).toBeInTheDocument()
  })

  it('clicking Kilidi Aç with empty input does nothing', async () => {
    const user = userEvent.setup()
    render(<Wrap />)
    await user.click(screen.getByRole('button', { name: /kilidi aç/i }))
    expect(screen.queryByText(/RELEASE yazınız/i)).not.toBeInTheDocument()
  })

  it('clicking Kilidi Aç with doc id opens TypedConfirmDialog', async () => {
    const user = userEvent.setup()
    render(<Wrap />)
    await user.type(screen.getByLabelText(/document id/i), '42')
    await user.click(screen.getByRole('button', { name: /kilidi aç/i }))
    expect(screen.getByLabelText(/RELEASE yazınız/i)).toBeInTheDocument()
  })

  it('confirmed release triggers POST and toasts', async () => {
    let capturedDocId: string | null = null
    server.use(
      http.post('http://localhost/api/locks/:doc_id/admin/force-release', ({ params }) => {
        capturedDocId = String(params.doc_id)
        return HttpResponse.json({ ok: true })
      }),
    )
    const user = userEvent.setup()
    render(<Wrap />)
    await user.type(screen.getByLabelText(/document id/i), '7')
    await user.click(screen.getByRole('button', { name: /kilidi aç/i }))
    await user.type(screen.getByLabelText(/RELEASE yazınız/i), 'RELEASE')
    await user.click(screen.getByRole('button', { name: /onayla/i }))
    await waitFor(() => expect(capturedDocId).toBe('7'))
  })

  it('404 from backend toasts warning "aktif lock yok"', async () => {
    server.use(
      http.post('http://localhost/api/locks/:doc_id/admin/force-release', () =>
        HttpResponse.json({ detail: 'no lock' }, { status: 404 }),
      ),
    )
    const user = userEvent.setup()
    render(<Wrap />)
    await user.type(screen.getByLabelText(/document id/i), '9')
    await user.click(screen.getByRole('button', { name: /kilidi aç/i }))
    await user.type(screen.getByLabelText(/RELEASE yazınız/i), 'RELEASE')
    await user.click(screen.getByRole('button', { name: /onayla/i }))
    await waitFor(() => expect(screen.getByText(/aktif lock yok/i)).toBeInTheDocument())
  })
})
