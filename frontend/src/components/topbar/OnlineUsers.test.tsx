import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { OnlineUsers } from './OnlineUsers'
import type { OnlineUser } from '@/lib/profileSchemas'

function mk(id: number, name: string): OnlineUser {
  return { id, username: name, avatar_color: '#3b82f6' }
}

describe('OnlineUsers', () => {
  it('renders nothing when list is empty', () => {
    const { container } = render(<OnlineUsers users={[]} maxVisible={5} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders all users when under maxVisible', () => {
    render(<OnlineUsers users={[mk(1, 'a'), mk(2, 'b')]} maxVisible={5} />)
    expect(screen.getByText('A')).toBeInTheDocument()
    expect(screen.getByText('B')).toBeInTheDocument()
    expect(screen.queryByText(/^\+\d/)).not.toBeInTheDocument()
  })

  it('renders +N chip when users exceed maxVisible', () => {
    const users = [mk(1, 'a'), mk(2, 'b'), mk(3, 'c'), mk(4, 'd'), mk(5, 'e'), mk(6, 'f'), mk(7, 'g')]
    render(<OnlineUsers users={users} maxVisible={5} />)
    expect(screen.getByText('+2')).toBeInTheDocument()
  })

  it('clicking +N opens popover with the overflow users only', async () => {
    // Bug fix: previously the popover repeated the visible avatars, which
    // contradicted the "+N" affordance. Now the chip's payload is just the
    // hidden users, matching the count it advertises.
    const user = userEvent.setup()
    const users = [mk(1, 'alice'), mk(2, 'bob'), mk(3, 'carol'), mk(4, 'dan'), mk(5, 'eve'), mk(6, 'fred')]
    render(<OnlineUsers users={users} maxVisible={5} />)
    await user.click(screen.getByRole('button', { name: /diğer 1 çevrimiçi/i }))
    expect(await screen.findByText(/fred/i)).toBeInTheDocument()
    // Visible users should NOT appear in the popover content (no duplicates).
    expect(screen.queryByText(/^alice$/)).not.toBeInTheDocument()
  })

  it('aria-label says how many are online', () => {
    render(<OnlineUsers users={[mk(1, 'a'), mk(2, 'b')]} maxVisible={5} />)
    expect(screen.getByLabelText('2 kullanıcı çevrimiçi')).toBeInTheDocument()
  })

  it('each avatar is a focusable button with the username as accessible name (a11y fix)', () => {
    // Bug fix: previously the tooltip wrapped an aria-hidden <Avatar> inside
    // a non-focusable <span>, so keyboard users could not trigger the tooltip
    // and screen readers saw no accessible name. The wrappers are now real
    // buttons whose aria-label exposes the username.
    render(<OnlineUsers users={[mk(1, 'alice'), mk(2, 'bob')]} maxVisible={5} />)
    expect(screen.getByRole('button', { name: 'alice' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'bob' })).toBeInTheDocument()
  })

  it('overflow chip carries an accessible label naming the hidden count (a11y fix)', () => {
    const users = [mk(1, 'a'), mk(2, 'b'), mk(3, 'c'), mk(4, 'd'), mk(5, 'e'), mk(6, 'f'), mk(7, 'g')]
    render(<OnlineUsers users={users} maxVisible={5} />)
    expect(screen.getByRole('button', { name: /diğer 2 çevrimiçi/i })).toBeInTheDocument()
  })
})
