 
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DiffPreviewDialog } from './DiffPreviewDialog'

describe('DiffPreviewDialog', () => {
  it('renders old and new JSON', () => {
    render(
      <DiffPreviewDialog
        open
        title="Test"
        oldValue={{ a: 1, b: 2 }}
        newValue={{ a: 1, b: 3 }}
        confirmWord="OK"
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />,
    )
    expect(screen.getByText(/eski/i)).toBeInTheDocument()
    expect(screen.getByText(/yeni/i)).toBeInTheDocument()
  })

  it('confirm requires typed word', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    render(
      <DiffPreviewDialog
        open
        title="t"
        oldValue={1}
        newValue={2}
        confirmWord="GO"
        onConfirm={onConfirm}
        onClose={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: /onayla/i })).toBeDisabled()
    await user.type(screen.getByLabelText(/GO yazınız/i), 'GO')
    expect(screen.getByRole('button', { name: /onayla/i })).not.toBeDisabled()
  })
})
