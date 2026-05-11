import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BadgeCard } from './BadgeCard'

describe('BadgeCard earned variant', () => {
  it('renders name + earned_at relative time', () => {
    render(
      <BadgeCard
        badge={{
          id: 'first_annotation', name: 'İlk Annotation',
          description: 'İlk kayıt başarıyla yapıldı.',
          earned_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
        }}
        variant="earned"
      />,
    )
    expect(screen.getByText('İlk Annotation')).toBeInTheDocument()
    expect(screen.getByText(/saat önce/)).toBeInTheDocument()
  })

  it('shows the description text', () => {
    render(
      <BadgeCard
        badge={{
          id: 'first_annotation', name: 'A',
          description: 'Yapıldı.', earned_at: '2026-05-11T00:00:00+00:00',
        }}
        variant="earned"
      />,
    )
    expect(screen.getByText('Yapıldı.')).toBeInTheDocument()
  })

  it('does NOT render grayscale class', () => {
    const { container } = render(
      <BadgeCard
        badge={{
          id: 'x', name: 'X', description: 'd', earned_at: '2026-05-11',
        }}
        variant="earned"
      />,
    )
    expect(container.firstChild).not.toHaveClass('grayscale')
  })
})

describe('BadgeCard locked variant', () => {
  it('renders grayscale + 🔒 + criterion text', () => {
    const { container } = render(
      <BadgeCard
        badge={{
          id: 'first_annotation', name: 'İlk Annotation',
          description: 'past tense',
          criterion: 'İlk anotasyon kaydını yap.',
        }}
        variant="locked"
      />,
    )
    expect(container.firstChild).toHaveClass('grayscale')
    expect(screen.getByLabelText('Kilitli')).toBeInTheDocument()
    expect(screen.getByText('İlk anotasyon kaydını yap.')).toBeInTheDocument()
    expect(screen.queryByText('past tense')).not.toBeInTheDocument()
  })

  it('falls back gracefully when criterion is null (body hidden)', () => {
    render(
      <BadgeCard
        badge={{ id: 'x', name: 'X', description: 'past', criterion: null }}
        variant="locked"
      />,
    )
    expect(screen.queryByText('past')).not.toBeInTheDocument()
  })

  it('has aria-disabled="true"', () => {
    const { container } = render(
      <BadgeCard
        badge={{ id: 'x', name: 'X', description: 'd', criterion: 'do x' }}
        variant="locked"
      />,
    )
    expect(container.firstChild).toHaveAttribute('aria-disabled', 'true')
  })
})
