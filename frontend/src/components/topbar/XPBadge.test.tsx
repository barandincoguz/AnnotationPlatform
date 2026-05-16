import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { XPBadge } from './XPBadge'

describe('XPBadge', () => {
  it('renders 0 when total is 0', () => {
    render(<XPBadge total={0} />)
    expect(screen.getByLabelText('Toplam XP')).toHaveTextContent('0')
  })

  it('formats with Turkish thousand separators', () => {
    render(<XPBadge total={1240} />)
    expect(screen.getByLabelText('Toplam XP')).toHaveTextContent('1.240')
  })

  it('formats million-scale values', () => {
    render(<XPBadge total={1234567} />)
    expect(screen.getByLabelText('Toplam XP')).toHaveTextContent('1.234.567')
  })

  it('renders the XP mono label', () => {
    render(<XPBadge total={5} />)
    expect(screen.getByText('XP')).toBeInTheDocument()
  })
})
