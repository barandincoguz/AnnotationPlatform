import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SortMenu } from './SortMenu'

describe('SortMenu', () => {
  it('opens the dropdown and lists every sort option', async () => {
    const user = userEvent.setup()
    render(
      <SortMenu
        tab="new"
        sort={{ by: 'tarih', order: 'desc' }}
        onChange={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: /sıralama/i }))
    expect(await screen.findByText('Tarih')).toBeInTheDocument()
    expect(screen.getByText('Konu')).toBeInTheDocument()
    expect(screen.getByText('Konu')).toBeInTheDocument()
    expect(screen.getByText(/karıştır/i)).toBeInTheDocument()
  })

  it('switching to a new key emits desc by default', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <SortMenu
        tab="new"
        sort={{ by: 'tarih', order: 'desc' }}
        onChange={onChange}
      />,
    )
    await user.click(screen.getByRole('button', { name: /sıralama/i }))
    await user.click(await screen.findByText('Konu'))
    expect(onChange).toHaveBeenCalledWith({ by: 'konu', order: 'desc' })
  })

  it('clicking the active key toggles direction', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <SortMenu
        tab="new"
        sort={{ by: 'tarih', order: 'desc' }}
        onChange={onChange}
      />,
    )
    await user.click(screen.getByRole('button', { name: /sıralama/i }))
    await user.click(await screen.findByText('Tarih'))
    expect(onChange).toHaveBeenCalledWith({ by: 'tarih', order: 'asc' })
  })

  it('clicking shuffle resets to shuffle key (no direction toggle)', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <SortMenu
        tab="new"
        sort={{ by: 'shuffle', order: 'desc' }}
        onChange={onChange}
      />,
    )
    await user.click(screen.getByRole('button', { name: /sıralama/i }))
    await user.click(await screen.findByText(/karıştır/i))
    // Clicking the active "shuffle" key should NOT toggle to "shuffle asc";
    // it stays a no-op shuffle (no second direction makes sense).
    expect(onChange).toHaveBeenCalledWith({ by: 'shuffle', order: 'desc' })
  })

  it('keys gated to review/verified are disabled on the new tab', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <SortMenu
        tab="new"
        sort={{ by: 'tarih', order: 'desc' }}
        onChange={onChange}
      />,
    )
    await user.click(screen.getByRole('button', { name: /sıralama/i }))
    const updated = await screen.findByText(/son güncelleme/i)
    const item = updated.closest('[role="menuitem"]')
    expect(item).toHaveAttribute('aria-disabled', 'true')
  })

  it('keys gated to review/verified are enabled on the review tab', async () => {
    const user = userEvent.setup()
    render(
      <SortMenu
        tab="review"
        sort={{ by: 'updated_at', order: 'desc' }}
        onChange={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: /sıralama/i }))
    const updated = await screen.findByText(/son güncelleme/i)
    const item = updated.closest('[role="menuitem"]')
    expect(item).not.toHaveAttribute('aria-disabled', 'true')
  })
})
