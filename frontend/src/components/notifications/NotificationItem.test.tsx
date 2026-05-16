import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { NotificationItem } from './NotificationItem'

const baseItem = {
  id: 1, kind: 'admin_announcement', title: 'Duyuru', body: null,
  data: null, is_read: false, created_at: '2026-05-11T00:00:00+00:00',
}

describe('NotificationItem', () => {
  it('renders title and relative time', () => {
    render(<NotificationItem item={baseItem} onMarkRead={vi.fn()} />)
    expect(screen.getByText('Duyuru')).toBeInTheDocument()
  })

  it('renders body when present', () => {
    render(<NotificationItem item={{ ...baseItem, body: 'detay' }} onMarkRead={vi.fn()} />)
    expect(screen.getByText('detay')).toBeInTheDocument()
  })

  it('shows mark-read button only when unread', () => {
    const { rerender } = render(<NotificationItem item={baseItem} onMarkRead={vi.fn()} />)
    expect(screen.getByLabelText(/okundu işaretle/i)).toBeInTheDocument()
    rerender(<NotificationItem item={{ ...baseItem, is_read: true }} onMarkRead={vi.fn()} />)
    expect(screen.queryByLabelText(/okundu işaretle/i)).not.toBeInTheDocument()
  })

  it('clicking mark-read calls onMarkRead with id', async () => {
    const onMarkRead = vi.fn()
    const user = userEvent.setup()
    render(<NotificationItem item={baseItem} onMarkRead={onMarkRead} />)
    await user.click(screen.getByLabelText(/okundu işaretle/i))
    expect(onMarkRead).toHaveBeenCalledWith(1)
  })

  it('uses kind-specific icon (badge_unlocked → 🏆)', () => {
    render(
      <NotificationItem
        item={{ ...baseItem, kind: 'badge_unlocked', title: 'Yeni rozet' }}
        onMarkRead={vi.fn()}
      />,
    )
    expect(screen.getByText('🏆')).toBeInTheDocument()
  })

  it('falls back to 🔔 for unknown kind', () => {
    render(
      <NotificationItem
        item={{ ...baseItem, kind: 'something_new' }}
        onMarkRead={vi.fn()}
      />,
    )
    expect(screen.getByText('🔔')).toBeInTheDocument()
  })

  it('unread items have visual emphasis (accent background + bold)', () => {
    const { container } = render(<NotificationItem item={baseItem} onMarkRead={vi.fn()} />)
    expect(container.firstChild).toHaveClass('font-medium')
    expect(container.firstChild).toHaveClass('bg-accent/5')
  })
})
