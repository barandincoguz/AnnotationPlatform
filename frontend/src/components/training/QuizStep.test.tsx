import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useTrainingStore } from '@/stores/trainingStore'
import { QuizStep } from './QuizStep'

const questions = [
  { id: 'q01', text: 'Soru 1', choices: ['a', 'b', 'c', 'd'] },
  { id: 'q02', text: 'Soru 2', choices: ['a', 'b', 'c', 'd'] },
  { id: 'q03', text: 'Soru 3', choices: ['a', 'b', 'c', 'd'] },
  { id: 'q04', text: 'Soru 4', choices: ['a', 'b', 'c', 'd'] },
  { id: 'q05', text: 'Soru 5', choices: ['a', 'b', 'c', 'd'] },
]

describe('QuizStep', () => {
  beforeEach(() => {
    useTrainingStore.getState().clear()
    useTrainingStore.setState({ questions, attemptId: 100, step: 'quiz' })
  })

  it('renders 5 fieldsets, 20 radios', () => {
    render(<QuizStep onSubmit={vi.fn()} isSubmitting={false} />)
    expect(screen.getAllByRole('group')).toHaveLength(5)
    expect(screen.getAllByRole('radio')).toHaveLength(20)
  })

  it('shows info banner', () => {
    render(<QuizStep onSubmit={vi.fn()} isSubmitting={false} />)
    expect(screen.getByText(/skorunu hepsini birden öğreneceksin/i)).toBeInTheDocument()
  })

  it('submit disabled until 5 answered', async () => {
    const user = userEvent.setup()
    render(<QuizStep onSubmit={vi.fn()} isSubmitting={false} />)
    const btn = screen.getByRole('button', { name: /cevapları gönder/i })
    expect(btn).toBeDisabled()
    const radios = screen.getAllByRole('radio')
    for (let i = 0; i < 5; i++) {
      await user.click(radios[i * 4]!)
    }
    expect(btn).not.toBeDisabled()
  })

  it('submit invokes onSubmit with answers', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<QuizStep onSubmit={onSubmit} isSubmitting={false} />)
    const radios = screen.getAllByRole('radio')
    for (let i = 0; i < 5; i++) {
      await user.click(radios[i * 4 + (i % 4)]!)
    }
    await user.click(screen.getByRole('button', { name: /cevapları gönder/i }))
    expect(onSubmit).toHaveBeenCalledWith({ q01: 0, q02: 1, q03: 2, q04: 3, q05: 0 })
  })

  it('shows result card with role=status when resultShown=quiz', () => {
    useTrainingStore.setState({ quizResult: { score: 3, total: 5 }, resultShown: { kind: 'quiz' } })
    render(<QuizStep onSubmit={vi.fn()} isSubmitting={false} />)
    expect(screen.getByText(/3 \/ 5/)).toBeInTheDocument()
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('Sonraki advances to doc step', async () => {
    const user = userEvent.setup()
    useTrainingStore.setState({ quizResult: { score: 4, total: 5 }, resultShown: { kind: 'quiz' } })
    render(<QuizStep onSubmit={vi.fn()} isSubmitting={false} />)
    await user.click(screen.getByRole('button', { name: /sonraki: doküman 1/i }))
    expect(useTrainingStore.getState().step).toBe('doc')
  })
})
