import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SortMenu } from './SortMenu'

// Phase 6: SortMenu is hidden behind a localStorage dev flag for
// every user except a developer that has explicitly opted in. The
// existing test surface still expects the menu to render — set the
// flag before each test, and clean up after.
beforeEach(() => {
  window.localStorage.setItem('a11n.dev_sort', '1')
})
afterEach(() => {
  window.localStorage.removeItem('a11n.dev_sort')
})

describe('SortMenu (dev flag gate)', () => {
  it('returns null when the dev flag is OFF (default state for users)', () => {
    window.localStorage.removeItem('a11n.dev_sort')
    const { container } = render(
      <SortMenu
        tab="new"
        sort={{ by: 'document_id', order: 'desc' }}
        onChange={vi.fn()}
      />,
    )
    // No trigger button, no content — fully invisible.
    expect(container.firstChild).toBeNull()
    expect(screen.queryByRole('button', { name: /sıralama/i })).not.toBeInTheDocument()
  })

  it('renders the trigger when the dev flag is ON', () => {
    render(
      <SortMenu
        tab="new"
        sort={{ by: 'document_id', order: 'desc' }}
        onChange={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: /sıralama/i })).toBeInTheDocument()
  })
})

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
    // Phase 6: document_id ("Özelge ID") is the cross-team canonical
    // default key and must surface in the dev-flag menu so a developer
    // can leave + return to it without a code change.
    expect(await screen.findByText('Özelge ID')).toBeInTheDocument()
    expect(screen.getByText('Tarih')).toBeInTheDocument()
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
