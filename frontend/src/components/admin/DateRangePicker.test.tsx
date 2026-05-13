/* eslint-disable react/display-name */
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DateRangePicker } from './DateRangePicker'

// Polyfills for Radix Select in jsdom — these APIs aren't implemented in jsdom
// but Radix calls them on pointer interactions.
beforeAll(() => {
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = () => false
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = () => undefined
  }
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => undefined
  }
})

describe('DateRangePicker', () => {
  it('renders preset options', async () => {
    const user = userEvent.setup()
    render(<DateRangePicker onChange={vi.fn()} value={null} />)
    await user.click(screen.getByRole('combobox'))
    expect(screen.getByText(/son 24 saat/i)).toBeInTheDocument()
    expect(screen.getByText(/son 7 gün/i)).toBeInTheDocument()
    expect(screen.getByText(/son 30 gün/i)).toBeInTheDocument()
    expect(screen.getByText(/özel/i)).toBeInTheDocument()
  })

  it('selecting a preset calls onChange with date_from/date_to', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<DateRangePicker onChange={onChange} value={null} />)
    await user.click(screen.getByRole('combobox'))
    await user.click(screen.getByText(/son 7 gün/i))
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        date_from: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
        date_to: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      }),
    )
  })
})
