import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TabStrip } from './TabStrip'

beforeEach(() => sessionStorage.clear())

describe('TabStrip', () => {
  it('renders 3 tab buttons in Turkish', () => {
    render(<TabStrip tab="new" onChange={vi.fn()} />)
    expect(screen.getByRole('tab', { name: /yeni/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /devam/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /tamamlanan/i })).toBeInTheDocument()
  })

  it('calls onChange when a different tab is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<TabStrip tab="new" onChange={onChange} />)
    await user.click(screen.getByRole('tab', { name: /devam/i }))
    expect(onChange).toHaveBeenCalledWith('review')
  })
})
