import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ReferencePanel } from './ReferencePanel'
import { makeReferenceItem } from '@/test/msw-handlers'
import type { ApiError } from '@/api/client'

// Shared defaults so every render covers all required props without
// flooding each test with boilerplate. Each test overrides only the
// fields it asserts on.
const baseProps = {
  onAdd: vi.fn(),
  onUpdate: vi.fn(),
  onRemove: vi.fn(),
  onSave: vi.fn(),
  onSkip: vi.fn(),
  onComplete: vi.fn(),
  canEdit: true,
  isSaving: false,
  isCompleting: false,
  error: null,
  draftSaveStatus: 'idle' as const,
  isValid: true,
  hasAnnotation: false,
  isCompleted: false,
}

describe('ReferencePanel', () => {
  it('renders one card per reference', () => {
    render(
      <ReferencePanel
        {...baseProps}
        refs={[makeReferenceItem({ madde: '1' }), makeReferenceItem({ madde: '2' })]}
      />,
    )
    expect(screen.getAllByText(/Referans #/)).toHaveLength(2)
  })

  it('shows empty state with hint when no refs', () => {
    render(<ReferencePanel {...baseProps} refs={[]} />)
    expect(screen.getByText(/henüz referans yok/i)).toBeInTheDocument()
  })

  it('"+ Yeni Referans" calls onAdd', () => {
    const onAdd = vi.fn()
    render(<ReferencePanel {...baseProps} refs={[]} onAdd={onAdd} />)
    fireEvent.click(screen.getByRole('button', { name: /yeni referans/i }))
    expect(onAdd).toHaveBeenCalled()
  })

  it('"Sakla" calls onSave', () => {
    const onSave = vi.fn()
    render(<ReferencePanel {...baseProps} refs={[makeReferenceItem()]} onSave={onSave} />)
    fireEvent.click(screen.getByRole('button', { name: /sakla/i }))
    expect(onSave).toHaveBeenCalled()
  })

  it('"Atla" calls onSkip', () => {
    const onSkip = vi.fn()
    render(<ReferencePanel {...baseProps} refs={[]} onSkip={onSkip} />)
    fireEvent.click(screen.getByRole('button', { name: /atla/i }))
    expect(onSkip).toHaveBeenCalled()
  })

  it('Sakla disabled while saving or when canEdit=false', () => {
    const { rerender } = render(
      <ReferencePanel {...baseProps} refs={[makeReferenceItem()]} isSaving={true} />,
    )
    expect(screen.getByRole('button', { name: /sakla|kaydediliyor/i })).toBeDisabled()
    rerender(<ReferencePanel {...baseProps} refs={[makeReferenceItem()]} canEdit={false} />)
    expect(screen.getByRole('button', { name: /sakla/i })).toBeDisabled()
  })

  it('shows ApiError.message inline when error is present', () => {
    const err = Object.assign(new Error('Geçersiz veri'), {
      name: 'ApiError',
      status: 422,
      code: 'validation_error',
    }) as unknown as ApiError
    render(<ReferencePanel {...baseProps} refs={[makeReferenceItem()]} error={err} />)
    expect(screen.getByText(/geçersiz veri/i)).toBeInTheDocument()
  })

  it('shows draft save status indicators', () => {
    const { rerender } = render(
      <ReferencePanel {...baseProps} refs={[]} draftSaveStatus="saving" />,
    )
    expect(screen.getByText(/taslak kaydediliyor/i)).toBeInTheDocument()

    rerender(<ReferencePanel {...baseProps} refs={[]} draftSaveStatus="saved" />)
    expect(screen.getByText(/taslak kaydedildi/i)).toBeInTheDocument()

    rerender(<ReferencePanel {...baseProps} refs={[]} draftSaveStatus="error" />)
    expect(screen.getByText(/taslak hata/i)).toBeInTheDocument()
  })
})

describe('ReferencePanel — validation gate (16c bug fix)', () => {
  it('Sakla disabled when an invalid ref is present', () => {
    const refs = [{ kanun_no: null, kanun_ad: null, madde: null, fikra: null, bent: null, source_text: 'metin' }]
    render(<ReferencePanel {...baseProps} refs={refs} isValid={false} />)
    expect(screen.getByRole('button', { name: /sakla/i })).toBeDisabled()
    expect(screen.getByText((_, el) =>
      el?.tagName === 'P' &&
      (el.textContent ?? '').includes('Kanun No') &&
      (el.textContent ?? '').includes('Kanun Adı'),
    )).toBeInTheDocument()
  })

  it('Sakla enabled when all refs valid', () => {
    const refs = [{ kanun_no: '5520', kanun_ad: null, madde: null, fikra: null, bent: null, source_text: 'metin' }]
    render(<ReferencePanel {...baseProps} refs={refs} isValid={true} />)
    expect(screen.getByRole('button', { name: /sakla/i })).not.toBeDisabled()
  })

  it('Sakla enabled when refs is empty (zero-ref legal)', () => {
    render(<ReferencePanel {...baseProps} refs={[]} isValid={true} />)
    expect(screen.getByRole('button', { name: /sakla/i })).not.toBeDisabled()
  })
})

describe('ReferencePanel — Tamamla / Geri Al toggle (paket-3g)', () => {
  it('hides the Tamamla button when there is no annotation row yet', () => {
    render(<ReferencePanel {...baseProps} refs={[]} hasAnnotation={false} />)
    expect(screen.queryByRole('button', { name: /tamamla|geri al/i })).toBeNull()
  })

  it('shows "Tamamla" when annotation exists and is not completed', () => {
    render(
      <ReferencePanel
        {...baseProps}
        refs={[makeReferenceItem()]}
        hasAnnotation={true}
        isCompleted={false}
      />,
    )
    expect(screen.getByRole('button', { name: /^tamamla$/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /geri al/i })).toBeNull()
  })

  it('shows "Geri Al" + completed badge when annotation is completed', () => {
    render(
      <ReferencePanel
        {...baseProps}
        refs={[makeReferenceItem()]}
        hasAnnotation={true}
        isCompleted={true}
      />,
    )
    expect(screen.getByRole('button', { name: /geri al/i })).toBeInTheDocument()
    expect(screen.getByText(/tamamlandı/i)).toBeInTheDocument()
  })

  it('calls onComplete on click', () => {
    const onComplete = vi.fn()
    render(
      <ReferencePanel
        {...baseProps}
        refs={[makeReferenceItem()]}
        hasAnnotation={true}
        onComplete={onComplete}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /tamamla/i }))
    expect(onComplete).toHaveBeenCalledTimes(1)
  })

  it('Tamamla disabled when refs are invalid (forward direction only)', () => {
    render(
      <ReferencePanel
        {...baseProps}
        refs={[makeReferenceItem()]}
        hasAnnotation={true}
        isCompleted={false}
        isValid={false}
      />,
    )
    expect(screen.getByRole('button', { name: /tamamla/i })).toBeDisabled()
  })

  it('Geri Al enabled even when refs invalid (reverse direction allowed)', () => {
    // Users must be able to undo a completion even if the editor currently
    // holds an invalid in-progress edit — otherwise they would be trapped.
    render(
      <ReferencePanel
        {...baseProps}
        refs={[makeReferenceItem()]}
        hasAnnotation={true}
        isCompleted={true}
        isValid={false}
      />,
    )
    expect(screen.getByRole('button', { name: /geri al/i })).not.toBeDisabled()
  })

  it('Tamamla disabled while another mutation is in flight', () => {
    const { rerender } = render(
      <ReferencePanel
        {...baseProps}
        refs={[makeReferenceItem()]}
        hasAnnotation={true}
        isCompleting={true}
      />,
    )
    expect(
      screen.getByRole('button', { name: /tamamlanıyor|tamamla/i }),
    ).toBeDisabled()
    rerender(
      <ReferencePanel
        {...baseProps}
        refs={[makeReferenceItem()]}
        hasAnnotation={true}
        canEdit={false}
      />,
    )
    expect(screen.getByRole('button', { name: /tamamla/i })).toBeDisabled()
  })
})
