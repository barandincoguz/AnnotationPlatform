import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DailyProgress } from './DailyProgress'

describe('DailyProgress', () => {
  it('renders nothing when target is 0', () => {
    const { container } = render(<DailyProgress today={5} target={0} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders progress bar with width %', () => {
    render(<DailyProgress today={3} target={10} />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '3')
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuemax', '10')
    expect(screen.getByText('3/10')).toBeInTheDocument()
  })

  it('clamps width to 100% when today >= target', () => {
    render(<DailyProgress today={15} target={10} />)
    const bar = screen.getByTestId('daily-progress-fill')
    expect(bar.style.width).toBe('100%')
  })

  it('shows "Bugün ✓" when today >= target', () => {
    render(<DailyProgress today={10} target={10} />)
    expect(screen.getByText(/Bugün ✓/)).toBeInTheDocument()
  })

  it('does NOT show "Bugün ✓" when below target', () => {
    render(<DailyProgress today={9} target={10} />)
    expect(screen.queryByText(/Bugün ✓/)).not.toBeInTheDocument()
  })
})
