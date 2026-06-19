import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useTrainingStore } from '@/stores/trainingStore'
import { AnnotateStep } from './AnnotateStep'

const goldDocs = [
  { gold_id: 'gold_a', content: 'Doc A içeriği — KVK 5/1-a uyarınca...' },
  { gold_id: 'gold_b', content: 'Doc B içeriği — KDV 29...' },
  { gold_id: 'gold_c', content: 'Doc C içeriği — GVK Geçici 67...' },
]

describe('AnnotateStep', () => {
  beforeEach(() => {
    useTrainingStore.getState().clear()
    useTrainingStore.setState({
      goldDocs,
      attemptId: 100,
      step: 'doc',
      docIndex: 0,
      docRefs: { gold_a: [], gold_b: [], gold_c: [] },
    })
  })

  it('renders current doc content', () => {
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    expect(screen.getByText(/doc a içeriği/i)).toBeInTheDocument()
  })

  it('renders + Yeni Referans button', () => {
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    expect(screen.getByRole('button', { name: /yeni referans/i })).toBeInTheDocument()
  })

  it('adding a reference renders form fields', async () => {
    const user = userEvent.setup()
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    await user.click(screen.getByRole('button', { name: /yeni referans/i }))
    expect(screen.getByLabelText(/^kanun no$/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/^metinden alıntı$/i)).toBeInTheDocument()
  })

  it('submit disabled if a reference has source_text but neither kanun_no nor kanun_ad', async () => {
    const user = userEvent.setup()
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    await user.click(screen.getByRole('button', { name: /yeni referans/i }))
    const sourceTextarea = screen.getByLabelText(/^metinden alıntı$/i)
    await user.type(sourceTextarea, 'metin')
    expect(screen.getByRole('button', { name: /gönder ve devam et/i })).toBeDisabled()
  })

  it('submit enabled when reference has source_text + kanun_ad only (no kanun_no)', async () => {
    const user = userEvent.setup()
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    await user.click(screen.getByRole('button', { name: /yeni referans/i }))
    await user.type(screen.getByLabelText(/^metinden alıntı$/i), 'metin')
    await user.type(screen.getByLabelText(/^kanun adı$/i), 'Kurumlar Vergisi Kanunu')
    expect(screen.getByRole('button', { name: /gönder ve devam et/i })).not.toBeDisabled()
  })

  it('submit enabled when reference has source_text + kanun_no only (no kanun_ad)', async () => {
    const user = userEvent.setup()
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    await user.click(screen.getByRole('button', { name: /yeni referans/i }))
    await user.type(screen.getByLabelText(/^metinden alıntı$/i), 'metin')
    await user.type(screen.getByLabelText(/^kanun no$/i), '5520')
    expect(screen.getByRole('button', { name: /gönder ve devam et/i })).not.toBeDisabled()
  })

  it('validates the source quote against the current training document', async () => {
    const user = userEvent.setup()
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    await user.click(screen.getByRole('button', { name: /yeni referans/i }))
    await user.type(screen.getByLabelText(/^metinden alıntı$/i), 'KVK 5/1-a')

    expect(screen.queryByText(/alıntı metni özelge gövdesinde bulunamadı/i)).not.toBeInTheDocument()
  })

  it('submit enabled with no references (zero-ref legal case)', () => {
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    expect(screen.getByRole('button', { name: /gönder ve devam et/i })).not.toBeDisabled()
  })

  it('submit click invokes onSubmit with gold_id and references', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<AnnotateStep onSubmit={onSubmit} onAdvance={vi.fn()} isSubmitting={false} />)
    await user.click(screen.getByRole('button', { name: /gönder ve devam et/i }))
    expect(onSubmit).toHaveBeenCalledWith('gold_a', [])
  })

  it('does not expose the answer key before submission', () => {
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    expect(screen.queryByRole('button', { name: /cevabı göster/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: /beklenen anotasyonlar/i })).not.toBeInTheDocument()
  })

  it('shows result card when current doc has resultShown', () => {
    useTrainingStore.setState({
      docResults: {
        gold_a: {
          passed: true,
          matched_count: 2,
          expected_count: 2,
          min_concept_count: 1,
          expected_concepts: [{ kanun_no: '5520', madde: '5' }],
        },
      },
      resultShown: { kind: 'doc', goldId: 'gold_a' },
    })
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    expect(screen.getByText(/2 \/ 2/)).toBeInTheDocument()
    expect(screen.getByText(/geçti/i)).toBeInTheDocument()
    expect(screen.getByRole('region', { name: /beklenen anotasyonlar/i })).toHaveTextContent(
      /kanun no: 5520.*madde: 5/i,
    )
  })

  it('Sonraki button advances doc index for docIndex<2', async () => {
    const user = userEvent.setup()
    const onAdvance = vi.fn()
    useTrainingStore.setState({
      docResults: {
        gold_a: {
          passed: true,
          matched_count: 1,
          expected_count: 1,
          min_concept_count: 1,
          expected_concepts: [{ kanun_no: '5520' }],
        },
      },
      resultShown: { kind: 'doc', goldId: 'gold_a' },
    })
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={onAdvance} isSubmitting={false} />)
    await user.click(screen.getByRole('button', { name: /sonraki: doküman 2/i }))
    expect(onAdvance).toHaveBeenCalledOnce()
  })

  it('on docIndex=2, last button is "Sonuçları Gör"', () => {
    useTrainingStore.setState({
      docIndex: 2,
      docResults: {
        gold_c: {
          passed: true,
          matched_count: 1,
          expected_count: 1,
          min_concept_count: 1,
          expected_concepts: [{ kanun_no: '193' }],
        },
      },
      resultShown: { kind: 'doc', goldId: 'gold_c' },
    })
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    expect(screen.getByRole('button', { name: /sonuçları gör/i })).toBeInTheDocument()
  })
})
