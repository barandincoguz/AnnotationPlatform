import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useTrainingStore } from '@/stores/trainingStore'
import { AnnotateStep } from './AnnotateStep'

const goldDocs = [
  { gold_id: 'gold_a', content: 'Doc A içeriği — KVK 5/1-a uyarınca...', expected_concepts: [{ kanun_no: '5520', madde: '5' }], min_concept_count: 1 },
  { gold_id: 'gold_b', content: 'Doc B içeriği — KDV 29...', expected_concepts: [{ kanun_no: '3065', madde: '29' }], min_concept_count: 1 },
  { gold_id: 'gold_c', content: 'Doc C içeriği — GVK Geçici 67...', expected_concepts: [{ kanun_no: '193', madde: 'Geçici 67' }], min_concept_count: 1 },
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

  it('Submit disabled if a reference has source_text but neither kanun_no nor kanun_ad', async () => {
    const user = userEvent.setup()
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    await user.click(screen.getByRole('button', { name: /yeni referans/i }))
    const sourceTextarea = screen.getByLabelText(/^metinden alıntı$/i)
    await user.type(sourceTextarea, 'metin')
    expect(screen.getByRole('button', { name: /submit/i })).toBeDisabled()
  })

  it('Submit enabled when reference has source_text + kanun_ad only (no kanun_no)', async () => {
    const user = userEvent.setup()
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    await user.click(screen.getByRole('button', { name: /yeni referans/i }))
    await user.type(screen.getByLabelText(/^metinden alıntı$/i), 'metin')
    await user.type(screen.getByLabelText(/^kanun adı$/i), 'Kurumlar Vergisi Kanunu')
    expect(screen.getByRole('button', { name: /submit/i })).not.toBeDisabled()
  })

  it('Submit enabled when reference has source_text + kanun_no only (no kanun_ad)', async () => {
    const user = userEvent.setup()
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    await user.click(screen.getByRole('button', { name: /yeni referans/i }))
    await user.type(screen.getByLabelText(/^metinden alıntı$/i), 'metin')
    await user.type(screen.getByLabelText(/^kanun no$/i), '5520')
    expect(screen.getByRole('button', { name: /submit/i })).not.toBeDisabled()
  })

  it('Submit enabled with no references (zero-ref legal case)', () => {
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    expect(screen.getByRole('button', { name: /submit/i })).not.toBeDisabled()
  })

  it('Submit click invokes onSubmit with gold_id and references', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<AnnotateStep onSubmit={onSubmit} onAdvance={vi.fn()} isSubmitting={false} />)
    await user.click(screen.getByRole('button', { name: /submit/i }))
    expect(onSubmit).toHaveBeenCalledWith('gold_a', [])
  })

  it('shows result card when current doc has resultShown', () => {
    useTrainingStore.setState({
      docResults: {
        gold_a: { passed: true, matched_count: 2, expected_count: 2, min_concept_count: 1 },
      },
      resultShown: { kind: 'doc', goldId: 'gold_a' },
    })
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    expect(screen.getByText(/2 \/ 2/)).toBeInTheDocument()
    expect(screen.getByText(/geçti/i)).toBeInTheDocument()
  })

  it('Sonraki button advances doc index for docIndex<2', async () => {
    const user = userEvent.setup()
    const onAdvance = vi.fn()
    useTrainingStore.setState({
      docResults: { gold_a: { passed: true, matched_count: 1, expected_count: 1, min_concept_count: 1 } },
      resultShown: { kind: 'doc', goldId: 'gold_a' },
    })
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={onAdvance} isSubmitting={false} />)
    await user.click(screen.getByRole('button', { name: /sonraki: doküman 2/i }))
    expect(onAdvance).toHaveBeenCalledOnce()
  })

  it('on docIndex=2, last button is "Sonuçları Gör"', () => {
    useTrainingStore.setState({
      docIndex: 2,
      docResults: { gold_c: { passed: true, matched_count: 1, expected_count: 1, min_concept_count: 1 } },
      resultShown: { kind: 'doc', goldId: 'gold_c' },
    })
    render(<AnnotateStep onSubmit={vi.fn()} onAdvance={vi.fn()} isSubmitting={false} />)
    expect(screen.getByRole('button', { name: /sonuçları gör/i })).toBeInTheDocument()
  })
})
