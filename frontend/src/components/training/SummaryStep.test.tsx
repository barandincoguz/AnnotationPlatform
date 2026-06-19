import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useTrainingStore } from '@/stores/trainingStore'
import { useAuthStore } from '@/stores/authStore'
import { SummaryStep } from './SummaryStep'
import { makeUser } from '@/test/msw-handlers'

const goldDocs = [
  { gold_id: 'gold_a', content: 'A' },
  { gold_id: 'gold_b', content: 'B' },
  { gold_id: 'gold_c', content: 'C' },
]

describe('SummaryStep', () => {
  beforeEach(() => {
    useTrainingStore.getState().clear()
    useTrainingStore.setState({
      attemptId: 100,
      step: 'summary',
      goldDocs,
      quizResult: { score: 4, total: 5, results: [
        { question_id: 'q01', user_choice: 0, correct_choice: 0, is_correct: true },
        { question_id: 'q02', user_choice: 1, correct_choice: 1, is_correct: true },
        { question_id: 'q03', user_choice: 0, correct_choice: 2, is_correct: false },
        { question_id: 'q04', user_choice: 3, correct_choice: 3, is_correct: true },
        { question_id: 'q05', user_choice: 1, correct_choice: 1, is_correct: true },
      ] },
      docResults: {
        gold_a: {
          passed: true, matched_count: 2, expected_count: 2, min_concept_count: 1,
          expected_concepts: [{ kanun_no: '5520' }],
        },
        gold_b: {
          passed: true, matched_count: 1, expected_count: 1, min_concept_count: 1,
          expected_concepts: [{ kanun_no: '3065' }],
        },
        gold_c: {
          passed: false, matched_count: 0, expected_count: 2, min_concept_count: 1,
          expected_concepts: [{ kanun_no: '193' }],
        },
      },
    })
  })

  it('PASS variant when has_passed_training=true', () => {
    useAuthStore.setState({ status: 'authed', user: makeUser({ has_passed_training: true }), error: null })
    render(<SummaryStep onAnnotate={vi.fn()} onRetry={vi.fn()} onBackToHelp={vi.fn()} />)
    expect(screen.getByText(/tebrikler/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /etiketlemeye başla/i })).toBeInTheDocument()
  })

  it('FAIL variant when has_passed_training=false', () => {
    useAuthStore.setState({ status: 'authed', user: makeUser({ has_passed_training: false }), error: null })
    render(<SummaryStep onAnnotate={vi.fn()} onRetry={vi.fn()} onBackToHelp={vi.fn()} />)
    expect(screen.getByText(/geçemedin/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /tekrar dene/i })).toBeInTheDocument()
  })

  it('DEGRADED hides breakdown', () => {
    useTrainingStore.setState({ degraded: true })
    useAuthStore.setState({ status: 'authed', user: makeUser({ has_passed_training: true }), error: null })
    render(<SummaryStep onAnnotate={vi.fn()} onRetry={vi.fn()} onBackToHelp={vi.fn()} />)
    expect(screen.getByText(/detaylar yeniden yüklenemedi/i)).toBeInTheDocument()
    expect(screen.queryByText(/quiz: 4/i)).not.toBeInTheDocument()
  })

  it('DEGRADED + passed -> Etiketlemeye başla', () => {
    useTrainingStore.setState({ degraded: true })
    useAuthStore.setState({ status: 'authed', user: makeUser({ has_passed_training: true }), error: null })
    render(<SummaryStep onAnnotate={vi.fn()} onRetry={vi.fn()} onBackToHelp={vi.fn()} />)
    expect(screen.getByRole('button', { name: /etiketlemeye başla/i })).toBeInTheDocument()
  })

  it('DEGRADED + not passed → Tekrar Dene', () => {
    useTrainingStore.setState({ degraded: true })
    useAuthStore.setState({ status: 'authed', user: makeUser({ has_passed_training: false }), error: null })
    render(<SummaryStep onAnnotate={vi.fn()} onRetry={vi.fn()} onBackToHelp={vi.fn()} />)
    expect(screen.getByRole('button', { name: /tekrar dene/i })).toBeInTheDocument()
  })

  it('Etiketlemeye başla -> onAnnotate', async () => {
    const user = userEvent.setup()
    const onAnnotate = vi.fn()
    useAuthStore.setState({ status: 'authed', user: makeUser({ has_passed_training: true }), error: null })
    render(<SummaryStep onAnnotate={onAnnotate} onRetry={vi.fn()} onBackToHelp={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: /etiketlemeye başla/i }))
    expect(onAnnotate).toHaveBeenCalledOnce()
  })

  it('Tekrar Dene → onRetry', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    useAuthStore.setState({ status: 'authed', user: makeUser({ has_passed_training: false }), error: null })
    render(<SummaryStep onAnnotate={vi.fn()} onRetry={onRetry} onBackToHelp={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: /tekrar dene/i }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
