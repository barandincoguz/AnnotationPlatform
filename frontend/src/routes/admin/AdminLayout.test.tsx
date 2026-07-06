 
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AdminLayout } from './AdminLayout'

const Wrap = ({ initialPath }: { initialPath: string }) => (
  <MemoryRouter
    initialEntries={[initialPath]}
    future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
  >
    <Routes>
      <Route path="/admin/*" element={<AdminLayout />}>
        <Route path="audit" element={<div>AUDIT_STUB</div>} />
        <Route path="users" element={<div>USERS_STUB</div>} />
        <Route path="feedback" element={<div>FEEDBACK_STUB</div>} />
      </Route>
    </Routes>
  </MemoryRouter>
)

describe('AdminLayout', () => {
  it('renders sidebar nav landmarks', () => {
    render(<Wrap initialPath="/admin/audit" />)
    expect(screen.getByRole('navigation', { name: /admin/i })).toBeInTheDocument()
  })

  it('renders sidebar group headings', () => {
    render(<Wrap initialPath="/admin/audit" />)
    expect(screen.getByText(/^operations$/i)).toBeInTheDocument()
    expect(screen.getByText(/^people$/i)).toBeInTheDocument()
    expect(screen.getByText(/^platform$/i)).toBeInTheDocument()
    expect(screen.getByText(/^training content$/i)).toBeInTheDocument()
  })

  it('renders sidebar links', () => {
    render(<Wrap initialPath="/admin/audit" />)
    expect(screen.getByRole('link', { name: /^audit/i })).toHaveAttribute('href', '/admin/audit')
    expect(screen.getByRole('link', { name: /^users/i })).toHaveAttribute('href', '/admin/users')
    expect(screen.getByRole('link', { name: /^feedback/i })).toHaveAttribute('href', '/admin/feedback')
    expect(screen.getByRole('link', { name: /^locks/i })).toHaveAttribute('href', '/admin/locks')
    expect(screen.getByRole('link', { name: /^events/i })).toHaveAttribute('href', '/admin/events')
    expect(screen.getByRole('link', { name: /^settings/i })).toHaveAttribute('href', '/admin/settings')
    expect(screen.getByRole('link', { name: /gold docs/i })).toHaveAttribute('href', '/admin/training/gold-docs')
    expect(screen.getByRole('link', { name: /^quiz/i })).toHaveAttribute('href', '/admin/training/quiz')
  })

  it('renders Outlet for child route', () => {
    render(<Wrap initialPath="/admin/users" />)
    expect(screen.getByText('USERS_STUB')).toBeInTheDocument()
  })

  it('renders skip link as first focusable element', () => {
    render(<Wrap initialPath="/admin/audit" />)
    const skip = screen.getByRole('link', { name: /içeriğe atla/i })
    expect(skip).toBeInTheDocument()
  })

  it('redirects /admin index to /admin/audit', () => {
    render(
      <MemoryRouter
        initialEntries={['/admin']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<Navigate to="/admin/audit" replace />} />
            <Route path="audit" element={<div>AUDIT_AFTER_REDIRECT</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByText('AUDIT_AFTER_REDIRECT')).toBeInTheDocument()
  })
})
