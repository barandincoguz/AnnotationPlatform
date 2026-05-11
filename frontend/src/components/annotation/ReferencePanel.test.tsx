import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ReferencePanel } from './ReferencePanel'
import { makeReferenceItem } from '@/test/msw-handlers'
import type { ApiError } from '@/api/client'

describe('ReferencePanel', () => {
  it('renders one card per reference', () => {
    render(
      <ReferencePanel
        refs={[
          makeReferenceItem({ madde: '1' }),
          makeReferenceItem({ madde: '2' }),
        ]}
        onAdd={vi.fn()}
        onUpdate={vi.fn()}
        onRemove={vi.fn()}
        onSave={vi.fn()}
        onSkip={vi.fn()}
        canEdit={true}
        isSaving={false}
        error={null}
        draftSaveStatus="idle"
      />,
    )
    expect(screen.getAllByText(/Referans #/)).toHaveLength(2)
  })

  it('shows empty state with hint when no refs', () => {
    render(
      <ReferencePanel
        refs={[]}
        onAdd={vi.fn()}
        onUpdate={vi.fn()}
        onRemove={vi.fn()}
        onSave={vi.fn()}
        onSkip={vi.fn()}
        canEdit={true}
        isSaving={false}
        error={null}
        draftSaveStatus="idle"
      />,
    )
    expect(screen.getByText(/henüz referans yok/i)).toBeInTheDocument()
  })

  it('"+ Yeni Referans" calls onAdd', () => {
    const onAdd = vi.fn()
    render(
      <ReferencePanel
        refs={[]}
        onAdd={onAdd}
        onUpdate={vi.fn()}
        onRemove={vi.fn()}
        onSave={vi.fn()}
        onSkip={vi.fn()}
        canEdit={true}
        isSaving={false}
        error={null}
        draftSaveStatus="idle"
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /yeni referans/i }))
    expect(onAdd).toHaveBeenCalled()
  })

  it('"Sakla" calls onSave', () => {
    const onSave = vi.fn()
    render(
      <ReferencePanel
        refs={[makeReferenceItem()]}
        onAdd={vi.fn()}
        onUpdate={vi.fn()}
        onRemove={vi.fn()}
        onSave={onSave}
        onSkip={vi.fn()}
        canEdit={true}
        isSaving={false}
        error={null}
        draftSaveStatus="idle"
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /sakla/i }))
    expect(onSave).toHaveBeenCalled()
  })

  it('"Atla" calls onSkip', () => {
    const onSkip = vi.fn()
    render(
      <ReferencePanel
        refs={[]}
        onAdd={vi.fn()}
        onUpdate={vi.fn()}
        onRemove={vi.fn()}
        onSave={vi.fn()}
        onSkip={onSkip}
        canEdit={true}
        isSaving={false}
        error={null}
        draftSaveStatus="idle"
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /atla/i }))
    expect(onSkip).toHaveBeenCalled()
  })

  it('Sakla disabled while saving or when canEdit=false', () => {
    const { rerender } = render(
      <ReferencePanel
        refs={[makeReferenceItem()]}
        onAdd={vi.fn()}
        onUpdate={vi.fn()}
        onRemove={vi.fn()}
        onSave={vi.fn()}
        onSkip={vi.fn()}
        canEdit={true}
        isSaving={true}
        error={null}
        draftSaveStatus="idle"
      />,
    )
    expect(screen.getByRole('button', { name: /sakla|kaydediliyor/i })).toBeDisabled()
    rerender(
      <ReferencePanel
        refs={[makeReferenceItem()]}
        onAdd={vi.fn()}
        onUpdate={vi.fn()}
        onRemove={vi.fn()}
        onSave={vi.fn()}
        onSkip={vi.fn()}
        canEdit={false}
        isSaving={false}
        error={null}
        draftSaveStatus="idle"
      />,
    )
    expect(screen.getByRole('button', { name: /sakla/i })).toBeDisabled()
  })

  it('shows ApiError.message inline when error is present', () => {
    const err = Object.assign(new Error('Geçersiz veri'), {
      name: 'ApiError',
      status: 422,
      code: 'validation_error',
    }) as unknown as ApiError
    render(
      <ReferencePanel
        refs={[makeReferenceItem()]}
        onAdd={vi.fn()}
        onUpdate={vi.fn()}
        onRemove={vi.fn()}
        onSave={vi.fn()}
        onSkip={vi.fn()}
        canEdit={true}
        isSaving={false}
        error={err}
        draftSaveStatus="idle"
      />,
    )
    expect(screen.getByText(/geçersiz veri/i)).toBeInTheDocument()
  })

  it('shows draft save status indicators', () => {
    const { rerender } = render(
      <ReferencePanel
        refs={[]}
        onAdd={vi.fn()}
        onUpdate={vi.fn()}
        onRemove={vi.fn()}
        onSave={vi.fn()}
        onSkip={vi.fn()}
        canEdit={true}
        isSaving={false}
        error={null}
        draftSaveStatus="saving"
      />,
    )
    expect(screen.getByText(/taslak kaydediliyor/i)).toBeInTheDocument()

    rerender(
      <ReferencePanel
        refs={[]}
        onAdd={vi.fn()}
        onUpdate={vi.fn()}
        onRemove={vi.fn()}
        onSave={vi.fn()}
        onSkip={vi.fn()}
        canEdit={true}
        isSaving={false}
        error={null}
        draftSaveStatus="saved"
      />,
    )
    expect(screen.getByText(/taslak kaydedildi/i)).toBeInTheDocument()

    rerender(
      <ReferencePanel
        refs={[]}
        onAdd={vi.fn()}
        onUpdate={vi.fn()}
        onRemove={vi.fn()}
        onSave={vi.fn()}
        onSkip={vi.fn()}
        canEdit={true}
        isSaving={false}
        error={null}
        draftSaveStatus="error"
      />,
    )
    expect(screen.getByText(/taslak hata/i)).toBeInTheDocument()
  })
})
