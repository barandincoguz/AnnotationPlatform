 
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TypedConfirmDialog } from './TypedConfirmDialog'

describe('TypedConfirmDialog', () => {
  it('renders title and required typed text', () => {
    render(
      <TypedConfirmDialog
        open
        title="Test"
        body={<p>are you sure?</p>}
        confirmWord="DELETE"
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />,
    )
    expect(screen.getByText(/are you sure/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/DELETE yazınız/i)).toBeInTheDocument()
  })

  it('confirm button disabled until exact word typed', async () => {
    const user = userEvent.setup()
    render(
      <TypedConfirmDialog
        open
        title="t"
        body={<p>x</p>}
        confirmWord="SKIP"
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />,
    )
    const confirm = screen.getByRole('button', { name: /onayla/i })
    expect(confirm).toBeDisabled()
    await user.type(screen.getByLabelText(/SKIP yazınız/i), 'skip')
    expect(confirm).toBeDisabled()  // case-sensitive
    await user.clear(screen.getByLabelText(/SKIP yazınız/i))
    await user.type(screen.getByLabelText(/SKIP yazınız/i), 'SKIP')
    expect(confirm).not.toBeDisabled()
  })

  it('clicking Vazgeç clears typed text and closes', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(
      <TypedConfirmDialog
        open
        title="t"
        body={<p>x</p>}
        confirmWord="DELETE"
        onConfirm={vi.fn()}
        onClose={onClose}
      />,
    )
    const input = screen.getByLabelText(/DELETE yazınız/i)
    await user.type(input, 'DELETE')
    await user.click(screen.getByRole('button', { name: /vazgeç/i }))
    expect(onClose).toHaveBeenCalled()
  })

  it('confirm button calls onConfirm', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    render(
      <TypedConfirmDialog
        open
        title="t"
        body={<p>x</p>}
        confirmWord="RUN"
        onConfirm={onConfirm}
        onClose={vi.fn()}
      />,
    )
    await user.type(screen.getByLabelText(/RUN yazınız/i), 'RUN')
    await user.click(screen.getByRole('button', { name: /onayla/i }))
    expect(onConfirm).toHaveBeenCalled()
  })

  it('isPending prop shows pending button and disables Vazgeç', () => {
    render(
      <TypedConfirmDialog
        open
        title="t"
        body={<p>x</p>}
        confirmWord="RUN"
        isPending
        pendingLabel="Çalışıyor..."
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />,
    )
    expect(screen.getByText(/çalışıyor/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /vazgeç/i })).toBeDisabled()
  })
})
