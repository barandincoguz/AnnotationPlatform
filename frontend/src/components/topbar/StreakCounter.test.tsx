import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StreakCounter } from './StreakCounter'

describe('StreakCounter', () => {
  it('renders "—" when current is 0', () => {
    render(<StreakCounter current={0} longest={0} />)
    expect(screen.getByLabelText(/streak/i)).toHaveTextContent('—')
  })

  it('renders the current count when > 0', () => {
    render(<StreakCounter current={3} longest={3} />)
    expect(screen.getByLabelText(/streak/i)).toHaveTextContent('3')
  })

  it('applies warning tier color for 4-6', () => {
    render(<StreakCounter current={5} longest={5} />)
    const el = screen.getByLabelText(/streak/i)
    expect(el.className).toMatch(/warning/i)
  })

  it('applies destructive tier color for 7+', () => {
    render(<StreakCounter current={7} longest={7} />)
    const el = screen.getByLabelText(/streak/i)
    expect(el.className).toMatch(/destructive/i)
  })

  it('shows longest in tooltip ONLY when longest > current', async () => {
    const user = userEvent.setup()
    render(<StreakCounter current={3} longest={12} />)
    const el = screen.getByLabelText(/streak/i)
    await user.hover(el)
    // Radix splits the tooltip text into multiple text nodes; assert via a
    // function matcher on the rendered text content of the tooltip.
    const tooltip = await screen.findByRole('tooltip')
    expect(tooltip.textContent).toMatch(/En uzun: 12 gün/)
  })

  it('does NOT render longest text when longest equals current', () => {
    render(<StreakCounter current={5} longest={5} />)
    expect(screen.queryByText(/en uzun/i)).not.toBeInTheDocument()
  })

  it('aria-label includes the count', () => {
    render(<StreakCounter current={3} longest={3} />)
    expect(screen.getByLabelText('3 gün streak')).toBeInTheDocument()
  })
})
