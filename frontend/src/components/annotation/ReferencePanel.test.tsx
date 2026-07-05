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
    // The first card is expanded by default, so it renders "Referans"
    expect(screen.getAllByText('Referans')).toHaveLength(1)
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getAllByText('2')).toHaveLength(2) // One in header, one in card badge

    // Click the second card to expand it
    fireEvent.click(screen.getAllByText('2')[1]!)
    // Now the second card is expanded, so it renders "Referans"
    expect(screen.getAllByText('Referans')).toHaveLength(1)
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

  it('"Kontrole Gönder" calls onSave', () => {
    const onSave = vi.fn()
    render(<ReferencePanel {...baseProps} refs={[makeReferenceItem()]} onSave={onSave} />)
    fireEvent.click(screen.getByRole('button', { name: /kontrole gönder/i }))
    expect(onSave).toHaveBeenCalled()
  })

  it('"Atla" calls onSkip', () => {
    const onSkip = vi.fn()
    render(<ReferencePanel {...baseProps} refs={[]} onSkip={onSkip} />)
    fireEvent.click(screen.getByRole('button', { name: /atla/i }))
    expect(onSkip).toHaveBeenCalled()
  })

  it('Kontrole Gönder disabled while saving or when canEdit=false', () => {
    const { rerender } = render(
      <ReferencePanel {...baseProps} refs={[makeReferenceItem()]} isSaving={true} />,
    )
    expect(screen.getByRole('button', { name: /kontrole gönder|gönderiliyor/i })).toBeDisabled()
    rerender(<ReferencePanel {...baseProps} refs={[makeReferenceItem()]} canEdit={false} />)
    expect(screen.getByRole('button', { name: /kontrole gönder/i })).toBeDisabled()
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
  it('Kontrole Gönder disabled when an invalid ref is present', () => {
    const refs = [{ kanun_no: null, kanun_ad: null, madde: null, fikra: null, bent: null, source_text: 'metin' }]
    render(<ReferencePanel {...baseProps} refs={refs} isValid={false} />)
    expect(screen.getByRole('button', { name: /kontrole gönder/i })).toBeDisabled()
    expect(screen.getByText((_, el) =>
      el?.tagName === 'P' &&
      (el.textContent ?? '').includes('Kanun No') &&
      (el.textContent ?? '').includes('Kanun Adı'),
    )).toBeInTheDocument()
  })

  it('Kontrole Gönder enabled when all refs valid', () => {
    const refs = [{ kanun_no: '5520', kanun_ad: null, madde: null, fikra: null, bent: null, source_text: 'metin' }]
    render(<ReferencePanel {...baseProps} refs={refs} isValid={true} />)
    expect(screen.getByRole('button', { name: /kontrole gönder/i })).not.toBeDisabled()
  })

  it('Kontrole Gönder enabled when refs is empty (zero-ref legal)', () => {
    render(<ReferencePanel {...baseProps} refs={[]} isValid={true} />)
    expect(screen.getByRole('button', { name: /kontrole gönder/i })).not.toBeDisabled()
  })
})

describe('ReferencePanel — Tamamlandı / Geri Al toggle (paket-3g)', () => {
  it('shows Tamamlandı button (disabled) on a draft-only doc with no refs yet', () => {
    // Phase 2 atomic complete supports first-time complete from a
    // draft-only state. The button now renders even when no annotation
    // row exists; completeDisabled gates it off when refs aren't valid.
    render(
      <ReferencePanel
        {...baseProps}
        refs={[]}
        hasAnnotation={false}
        isValid={false}
      />,
    )
    const btn = screen.getByRole('button', { name: /^tamamlandı$/i })
    expect(btn).toBeInTheDocument()
    expect(btn).toBeDisabled()
  })

  it('enables Tamamlandı button on a draft-only doc with valid refs (atomic complete)', () => {
    render(
      <ReferencePanel
        {...baseProps}
        refs={[makeReferenceItem()]}
        hasAnnotation={false}
        isValid={true}
      />,
    )
    const btn = screen.getByRole('button', { name: /^tamamlandı$/i })
    expect(btn).toBeEnabled()
  })

  it('shows "Tamamlandı" when annotation exists and is not completed', () => {
    render(
      <ReferencePanel
        {...baseProps}
        refs={[makeReferenceItem()]}
        hasAnnotation={true}
        isCompleted={false}
      />,
    )
    expect(screen.getByRole('button', { name: /^tamamlandı$/i })).toBeInTheDocument()
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
    fireEvent.click(screen.getByRole('button', { name: /tamamlandı/i }))
    expect(onComplete).toHaveBeenCalledTimes(1)
  })

  it('Tamamlandı disabled when refs are invalid (forward direction only)', () => {
    render(
      <ReferencePanel
        {...baseProps}
        refs={[makeReferenceItem()]}
        hasAnnotation={true}
        isCompleted={false}
        isValid={false}
      />,
    )
    expect(screen.getByRole('button', { name: /tamamlandı/i })).toBeDisabled()
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

  it('Tamamlandı disabled while another mutation is in flight', () => {
    const { rerender } = render(
      <ReferencePanel
        {...baseProps}
        refs={[makeReferenceItem()]}
        hasAnnotation={true}
        isCompleting={true}
      />,
    )
    expect(
      screen.getByRole('button', { name: /tamamlanıyor|tamamlandı/i }),
    ).toBeDisabled()
    rerender(
      <ReferencePanel
        {...baseProps}
        refs={[makeReferenceItem()]}
        hasAnnotation={true}
        canEdit={false}
      />,
    )
    expect(screen.getByRole('button', { name: /tamamlandı/i })).toBeDisabled()
  })
})
