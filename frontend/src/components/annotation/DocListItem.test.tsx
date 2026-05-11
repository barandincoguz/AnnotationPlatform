import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { DocListItem } from './DocListItem'
import { makeFeedItem } from '@/test/msw-handlers'

describe('DocListItem', () => {
  it('renders sayi + tarih + konu + vergi_turu', () => {
    render(
      <DocListItem
        item={makeFeedItem({
          sayi: 1234,
          tarih: '2025-05-22',
          konu: 'Vergi Usul Kanunu uyarınca düzenlenen rapor',
          vergi_turu: 'KDV',
        })}
        isSelected={false}
        onClick={vi.fn()}
      />,
    )
    expect(screen.getByText(/1234/)).toBeInTheDocument()
    expect(screen.getByText(/Vergi Usul Kanunu/i)).toBeInTheDocument()
    expect(screen.getByText('KDV')).toBeInTheDocument()
  })

  it('shows verified badge when is_completed=true', () => {
    render(
      <DocListItem
        item={makeFeedItem({ has_annotation: true, is_completed: true })}
        isSelected={false}
        onClick={vi.fn()}
      />,
    )
    expect(screen.getByLabelText(/tamamland.*/i)).toBeInTheDocument()
  })

  it('shows review badge when has_annotation && !is_completed', () => {
    render(
      <DocListItem
        item={makeFeedItem({ has_annotation: true, is_completed: false })}
        isSelected={false}
        onClick={vi.fn()}
      />,
    )
    expect(screen.getByLabelText(/devam ediyor/i)).toBeInTheDocument()
  })

  it('shows new badge when no annotation', () => {
    render(
      <DocListItem
        item={makeFeedItem({ has_annotation: false })}
        isSelected={false}
        onClick={vi.fn()}
      />,
    )
    expect(screen.getByLabelText(/yeni/i)).toBeInTheDocument()
  })

  it('shows last editor attribution when present', () => {
    render(
      <DocListItem
        item={makeFeedItem({
          has_annotation: true,
          last_editor_username: 'Ahmet',
          updated_at: '2026-05-11T11:00:00Z',
        })}
        isSelected={false}
        onClick={vi.fn()}
      />,
    )
    expect(screen.getByText(/Ahmet/i)).toBeInTheDocument()
  })

  it('calls onClick when clicked', () => {
    const onClick = vi.fn()
    render(
      <DocListItem
        item={makeFeedItem({ document_id: 'doc-XYZ' })}
        isSelected={false}
        onClick={onClick}
      />,
    )
    fireEvent.click(screen.getByRole('button'))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('applies selected styling when isSelected', () => {
    render(<DocListItem item={makeFeedItem()} isSelected={true} onClick={vi.fn()} />)
    const button = screen.getByRole('button')
    expect(button.className).toMatch(/bg-accent|border-primary/)
  })
})
