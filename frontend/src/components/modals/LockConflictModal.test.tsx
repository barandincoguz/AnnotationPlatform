import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { LockConflictModal } from './LockConflictModal'

describe('LockConflictModal', () => {
  it('renders other-user message and "Listeye dön" button', () => {
    render(
      <LockConflictModal
        open={true}
        conflictUsername="ahmet"
        isSameUser={false}
        onClose={vi.fn()}
      />,
    )
    expect(screen.getByText(/ahmet/i)).toBeInTheDocument()
    expect(screen.getByText(/düzenliyor/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /listeye dön/i })).toBeInTheDocument()
  })

  it('shows same-user wording when isSameUser=true (F8)', () => {
    render(
      <LockConflictModal open={true} conflictUsername="me" isSameUser={true} onClose={vi.fn()} />,
    )
    expect(screen.getByText(/başka sekmede/i)).toBeInTheDocument()
  })

  it('calls onClose when "Listeye dön" is clicked', () => {
    const onClose = vi.fn()
    render(
      <LockConflictModal
        open={true}
        conflictUsername="ahmet"
        isSameUser={false}
        onClose={onClose}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /listeye dön/i }))
    expect(onClose).toHaveBeenCalled()
  })

  it('does not render when open=false', () => {
    render(
      <LockConflictModal
        open={false}
        conflictUsername="ahmet"
        isSameUser={false}
        onClose={vi.fn()}
      />,
    )
    expect(screen.queryByRole('button', { name: /listeye dön/i })).toBeNull()
  })
})
