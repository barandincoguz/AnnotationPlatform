/* eslint-disable react/display-name */
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { server } from '@/test/msw-server'
import { UsersPage } from './UsersPage'

const Wrap = () => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <Toaster />
    <UsersPage />
  </QueryClientProvider>
)

beforeEach(() => {
  server.use(
    http.get('http://localhost/api/admin/users', () => HttpResponse.json({
      users: [
        { id: 1, username: 'root', email: null, role: 'admin', is_active: true,
          has_seen_manual: true, has_passed_training: true, avatar_color: null,
          created_at: '2026-05-01T00:00:00+00:00' },
        { id: 2, username: 'alice', email: 'alice@x.com', role: 'user', is_active: true,
          has_seen_manual: false, has_passed_training: false, avatar_color: '#22c55e',
          created_at: '2026-05-02T00:00:00+00:00' },
      ],
      total: 2,
    })),
  )
})

describe('UsersPage', () => {
  it('renders the users table', async () => {
    render(<Wrap />)
    await waitFor(() => expect(screen.getByText('alice')).toBeInTheDocument())
    expect(screen.getByText('root')).toBeInTheDocument()
  })

  it('promote action triggers POST and invalidates', async () => {
    let called = false
    server.use(
      http.post('http://localhost/api/admin/users/2/promote', () => {
        called = true
        return HttpResponse.json({ ok: true })
      }),
    )
    const user = userEvent.setup()
    render(<Wrap />)
    await waitFor(() => expect(screen.getByText('alice')).toBeInTheDocument())
    const rowMenuBtns = screen.getAllByRole('button', { name: /eylemler/i })
    await user.click(rowMenuBtns[1]!)  // alice is row 2 (index 1)
    await user.click(screen.getByRole('menuitem', { name: /admin yap/i }))
    await user.type(screen.getByLabelText(/PROMOTE yazınız/i), 'PROMOTE')
    await user.click(screen.getByRole('button', { name: /yetki ver/i }))
    await waitFor(() => expect(called).toBe(true))
  })

  it('last-admin demote shows 400 toast', async () => {
    server.use(
      http.post('http://localhost/api/admin/users/1/demote', () =>
        HttpResponse.json({ detail: 'cannot demote the last active admin' }, { status: 400 }),
      ),
    )
    const user = userEvent.setup()
    render(<Wrap />)
    await waitFor(() => expect(screen.getByText('root')).toBeInTheDocument())
    const rowMenuBtns = screen.getAllByRole('button', { name: /eylemler/i })
    await user.click(rowMenuBtns[0]!)  // root row (index 0)
    await user.click(screen.getByRole('menuitem', { name: /admin yetkisini kaldır/i }))
    await user.type(screen.getByLabelText(/DEMOTE yazınız/i), 'DEMOTE')
    await user.click(screen.getByRole('button', { name: /kaldır/i }))
    await waitFor(() =>
      expect(screen.getByText(/son admin/i)).toBeInTheDocument(),
    )
  })

  it('invite rotate shows new code in dialog', async () => {
    server.use(
      http.post('http://localhost/api/admin/invite/rotate', () =>
        HttpResponse.json({ ok: true, new_code: 'NEW-CODE-123' }),
      ),
    )
    const user = userEvent.setup()
    render(<Wrap />)
    await waitFor(() => expect(screen.getByText('alice')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /davet linki üret/i }))
    await waitFor(() => expect(screen.getByText(/NEW-CODE-123/i)).toBeInTheDocument())
  })
})
