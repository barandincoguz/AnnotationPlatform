import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatCards } from './StatCards'
import { makeProfile } from '@/test/msw-handlers'

describe('StatCards', () => {
  it('renders XP, Streak, Bugün, Rozet cards', () => {
    render(<StatCards profile={makeProfile()} />)
    expect(screen.getByText(/Toplam XP/i)).toBeInTheDocument()
    expect(screen.getByText('Streak')).toBeInTheDocument()
    expect(screen.getByText('Bugün')).toBeInTheDocument()
    expect(screen.getByText(/Toplam Rozet/i)).toBeInTheDocument()
  })

  it('formats XP with TR locale', () => {
    render(<StatCards profile={makeProfile({ xp: { total: 1234567 } })} />)
    expect(screen.getByText(/1\.234\.567/)).toBeInTheDocument()
  })

  it('shows "Günlük hedef kapalı" when daily_target is 0', () => {
    render(<StatCards profile={makeProfile({ today: { save: 5, complete: 0, review: 0, skip: 0, daily_target: 0 } })} />)
    expect(screen.getByText(/Günlük hedef kapalı/)).toBeInTheDocument()
  })

  it('shows progress bar when daily_target > 0', () => {
    render(<StatCards profile={makeProfile({ today: { save: 3, complete: 0, review: 0, skip: 0, daily_target: 10 } })} />)
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })

  it('shows longest in StreakCard subtitle', () => {
    render(<StatCards profile={makeProfile({ streak: { current: 3, longest: 12, last_active_date: '2026-05-11' } })} />)
    expect(screen.getByText(/En uzun.*12/)).toBeInTheDocument()
  })

  it('shows badge count', () => {
    render(<StatCards profile={makeProfile()} />)
    // 4f: cards now render the IconOrb + label in one row and the count in a
    // sibling row, so the prior `previousElementSibling` walk no longer maps
    // to the count node. Verify by scoping to the card that owns the label.
    const rozetLabel = screen.getByText('Toplam Rozet')
    const card = rozetLabel.closest('div[class*="rounded"]')
    expect(card?.textContent).toMatch(/1/)
  })
})
