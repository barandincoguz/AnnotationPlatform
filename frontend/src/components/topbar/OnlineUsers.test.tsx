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

  it('clicking +N opens popover with all online users', async () => {
    const user = userEvent.setup()
    const users = [mk(1, 'alice'), mk(2, 'bob'), mk(3, 'carol'), mk(4, 'dan'), mk(5, 'eve'), mk(6, 'fred')]
    render(<OnlineUsers users={users} maxVisible={5} />)
    await user.click(screen.getByText('+1'))
    expect(await screen.findByText(/fred/i)).toBeInTheDocument()
  })

  it('aria-label says how many are online', () => {
    render(<OnlineUsers users={[mk(1, 'a'), mk(2, 'b')]} maxVisible={5} />)
    expect(screen.getByLabelText('2 kullanıcı çevrimiçi')).toBeInTheDocument()
  })
})
