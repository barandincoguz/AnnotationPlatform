import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { DocListItem } from './DocListItem'
import { makeFeedItem } from '@/test/msw-handlers'

describe('DocListItem', () => {
  it('renders document_id + tarih + konu + vergi_turu', () => {
    // The list row now leads with document_id (evrakOid) — the project
    // dropped the per-year "sayi" because it isn't unique across years
    // and was misleading users.
    render(
      <DocListItem
        item={makeFeedItem({
          document_id: '17h2sm8cdz11kq',
          tarih: '2025-05-22',
          konu: 'Vergi Usul Kanunu uyarınca düzenlenen rapor',
          vergi_turu: 'KDV',
        })}
        isSelected={false}
        onClick={vi.fn()}
      />,
    )
    expect(screen.getByText('17h2sm8cdz11kq')).toBeInTheDocument()
    expect(screen.getByText(/Vergi Usul Kanunu/i)).toBeInTheDocument()
    expect(screen.getByText('KDV')).toBeInTheDocument()
  })

  // === Phase 3: workflow_state branding ===
  // Each enum value gets a dedicated icon + accessible label. The test
  // asserts the label because the icon is `aria-hidden` and the row's
  // `aria-label` carries the screen-reader-visible status text.

  it("renders 'tamamlandı' status when workflow_state='verified'", () => {
    render(
      <DocListItem
        item={makeFeedItem({
          workflow_state: 'verified',
          has_annotation: true,
          is_completed: true,
        })}
        isSelected={false}
        onClick={vi.fn()}
      />,
    )
    expect(screen.getByLabelText(/tamamland.*/i)).toBeInTheDocument()
  })

  it("renders 'devam ediyor' status when workflow_state='review'", () => {
    render(
      <DocListItem
        item={makeFeedItem({
          workflow_state: 'review',
          has_annotation: true,
          is_completed: false,
        })}
        isSelected={false}
        onClick={vi.fn()}
      />,
    )
    expect(screen.getByLabelText(/devam ediyor/i)).toBeInTheDocument()
  })

  it("renders 'taslak' status when workflow_state='draft' (Phase 1 new state)", () => {
    // 'draft' = caller has refs in a draft row but no shared annotation.
    // Surfaces in Devam Eden tab alongside 'review' entries; the row
    // label distinguishes them.
    render(
      <DocListItem
        item={makeFeedItem({
          workflow_state: 'draft',
          has_draft: true,
          has_annotation: false,
        })}
        isSelected={false}
        onClick={vi.fn()}
      />,
    )
    expect(screen.getByLabelText(/taslak/i)).toBeInTheDocument()
  })

  it("renders 'yeni' status when workflow_state='new'", () => {
    render(
      <DocListItem
        item={makeFeedItem({ workflow_state: 'new' })}
        isSelected={false}
        onClick={vi.fn()}
      />,
    )
    expect(screen.getByLabelText(/yeni/i)).toBeInTheDocument()
  })

  it('shows last editor attribution for review state', () => {
    render(
      <DocListItem
        item={makeFeedItem({
          workflow_state: 'review',
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

  it('does NOT show last editor attribution for draft-only state', () => {
    // A 'draft' row has no shared annotation, so there is no "last
    // editor" to attribute. The attribution label must stay hidden.
    render(
      <DocListItem
        item={makeFeedItem({
          workflow_state: 'draft',
          has_draft: true,
          last_editor_username: 'Ahmet',  // present but ignored
          updated_at: '2026-05-11T11:00:00Z',
        })}
        isSelected={false}
        onClick={vi.fn()}
      />,
    )
    expect(screen.queryByText(/Ahmet/i)).not.toBeInTheDocument()
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
    expect(button.className).toMatch(/bg-secondary|bg-accent|border-primary/)
  })
})
