import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AttributionLabel } from './AttributionLabel'

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-05-11T12:00:00Z'))
})
afterEach(() => vi.useRealTimers())

describe('AttributionLabel', () => {
  it('renders username + relative date', () => {
    render(<AttributionLabel username="Ahmet" date="2026-05-11T10:00:00Z" />)
    expect(screen.getByText(/Ahmet/i)).toBeInTheDocument()
    expect(screen.getByText(/saat önce/i)).toBeInTheDocument()
  })

  it('renders dash when username is null', () => {
    render(<AttributionLabel username={null} date="2026-05-11T10:00:00Z" />)
    expect(screen.getByText('-')).toBeInTheDocument()
  })
})
