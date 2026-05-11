import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ProfileDropdown } from './ProfileDropdown'
import type { UserSection } from '@/lib/profileSchemas'

vi.mock('sonner', () => ({ toast: { success: vi.fn() } }))

function wrap() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

const testUser: UserSection = {
  id: 1, username: 'tester', role: 'user', avatar_color: '#3b82f6',
}

describe('ProfileDropdown', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows no unread dot when unreadCount=0', () => {
    render(<ProfileDropdown user={testUser} unreadCount={0} />, { wrapper: wrap() })
    expect(screen.queryByTestId('unread-dot')).not.toBeInTheDocument()
  })

  it('shows unread dot with count up to 9+', () => {
    const { rerender, unmount } = render(
      <ProfileDropdown user={testUser} unreadCount={3} />,
      { wrapper: wrap() },
    )
    expect(screen.getByTestId('unread-dot')).toHaveTextContent('3')
    rerender(<ProfileDropdown user={testUser} unreadCount={15} />)
    expect(screen.getByTestId('unread-dot')).toHaveTextContent('9+')
    unmount()
  })

  it('opens dropdown and shows the four sections', async () => {
    const user = userEvent.setup()
    render(<ProfileDropdown user={testUser} unreadCount={0} />, { wrapper: wrap() })
    await user.click(screen.getByLabelText('Profil menüsü'))
    // Bildirimler appears as a section label
    expect(await screen.findByText(/Bildirimler/)).toBeInTheDocument()
    expect(screen.getByText('Profilim')).toBeInTheDocument()
    expect(screen.getByText('Yardım')).toBeInTheDocument()
    expect(screen.getByText('Çıkış')).toBeInTheDocument()
  })

  it('Profilim links to /me', async () => {
    const user = userEvent.setup()
    render(<ProfileDropdown user={testUser} unreadCount={0} />, { wrapper: wrap() })
    await user.click(screen.getByLabelText('Profil menüsü'))
    const link = await screen.findByText('Profilim')
    const anchor = link.closest('a')
    expect(anchor?.getAttribute('href')).toBe('/me')
  })
})
