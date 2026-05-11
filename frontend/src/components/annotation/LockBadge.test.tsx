import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LockBadge } from './LockBadge'

describe('LockBadge', () => {
  it('renders lock icon + username', () => {
    render(<LockBadge username="baran" acquiredAt="2026-05-11T10:00:00Z" />)
    expect(screen.getByText(/baran/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/kilitli/i)).toBeInTheDocument()
  })
})
