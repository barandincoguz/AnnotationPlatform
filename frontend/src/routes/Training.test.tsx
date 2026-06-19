import { describe, it, expect, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  mockAuthedUser,
  mockTrainingStartLockedOut,
  mockTrainingStartAlreadyPassed,
  mockAnnotateSubmitFail,
  mockQuizSubmitAlreadySubmitted,
  makeStartResponse,
} from '@/test/msw-handlers'
import { server } from '@/test/msw-server'
import { renderWithProviders } from '@/test/render'
import { Training } from './Training'
import { useTrainingStore } from '@/stores/trainingStore'
import { useAuthStore } from '@/stores/authStore'

const FRESH_USER = {
  id: 1,
  username: 't',
  email: null,
  role: 'user' as const,
  is_active: true,
  avatar_color: '#000',
  has_seen_manual: true,
  has_passed_training: false,
  created_at: '2026-05-01T00:00:00+00:00',
}

beforeEach(() => {
  sessionStorage.clear()
  useTrainingStore.getState().clear()
})

describe('Training route — happy path', () => {
  it('full PASS flow: start → quiz → 3 docs → SummaryPass → annotate', async () => {
    const user = userEvent.setup()
    useAuthStore.setState({ status: 'authed', user: FRESH_USER, error: null })
    server.use(mockAuthedUser({ has_seen_manual: true, has_passed_training: false }))

    renderWithProviders(<Training />, { initialEntries: ['/training'] })

    await waitFor(() => expect(screen.getByText(/1 deneme harcanır/i)).toBeInTheDocument())
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: /^başla$/i }))

    await waitFor(() => expect(screen.getAllByRole('group')).toHaveLength(5))
    for (let i = 0; i < 5; i++) {
      const radios = screen.getAllByRole('radio')
      await user.click(radios[i * 4]!)
    }
    await user.click(screen.getByRole('button', { name: /cevapları gönder/i }))

    await waitFor(() => expect(screen.getByText(/4 \/ 5/)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /sonraki: doküman 1/i }))

    await waitFor(() => expect(screen.getByText(/doc a içeriği/i)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /gönder ve devam et/i }))
    await waitFor(() => expect(screen.getByText(/durum:/i)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /sonraki: doküman 2/i }))

    await waitFor(() => expect(screen.getByText(/doc b içeriği/i)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /gönder ve devam et/i }))
    await waitFor(() => expect(screen.getByText(/durum:/i)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /sonraki: doküman 3/i }))

    await waitFor(() => expect(screen.getByText(/doc c içeriği/i)).toBeInTheDocument())
    server.use(mockAuthedUser({ has_seen_manual: true, has_passed_training: true }))
    await user.click(screen.getByRole('button', { name: /gönder ve devam et/i }))
    await waitFor(() => expect(screen.getByText(/durum:/i)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /sonuçları gör/i }))

    await waitFor(() => expect(screen.getByText(/tebrikler/i)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /etiketlemeye başla/i }))

    await waitFor(() => expect(screen.getByTestId('route-root')).toBeInTheDocument())
    expect(sessionStorage.getItem('training-attempt-v1')).toBeNull()
  })
})

describe('Training route — fail path', () => {
  it('SummaryFail with Tekrar Dene visible', async () => {
    const user = userEvent.setup()
    useAuthStore.setState({ status: 'authed', user: FRESH_USER, error: null })
    server.use(mockAnnotateSubmitFail(), mockAuthedUser({ has_seen_manual: true, has_passed_training: false }))

    renderWithProviders(<Training />, { initialEntries: ['/training'] })
    await waitFor(() => expect(screen.getByText(/1 deneme harcanır/i)).toBeInTheDocument())
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: /^başla$/i }))

    await waitFor(() => expect(screen.getAllByRole('group')).toHaveLength(5))
    for (let i = 0; i < 5; i++) {
      await user.click(screen.getAllByRole('radio')[i * 4]!)
    }
    await user.click(screen.getByRole('button', { name: /cevapları gönder/i }))
    await waitFor(() => expect(screen.getByText(/skor:/i)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /sonraki: doküman 1/i }))

    await waitFor(() => expect(screen.getByText(/doc a içeriği/i)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /gönder ve devam et/i }))
    await waitFor(() => expect(screen.getByText(/durum:/i)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /sonraki: doküman 2/i }))

    await waitFor(() => expect(screen.getByText(/doc b içeriği/i)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /gönder ve devam et/i }))
    await waitFor(() => expect(screen.getByText(/durum:/i)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /sonraki: doküman 3/i }))

    await waitFor(() => expect(screen.getByText(/doc c içeriği/i)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /gönder ve devam et/i }))
    await waitFor(() => expect(screen.getByText(/durum:/i)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /sonuçları gör/i }))

    await waitFor(() => expect(screen.getByText(/geçemedin/i)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /tekrar dene/i })).toBeInTheDocument()
  })
})

describe('Training route — locked out', () => {
  it('routes to LockedOutScreen on 403', async () => {
    const user = userEvent.setup()
    useAuthStore.setState({ status: 'authed', user: FRESH_USER, error: null })
    server.use(mockTrainingStartLockedOut(), mockAuthedUser({ has_seen_manual: true, has_passed_training: false }))

    renderWithProviders(<Training />, { initialEntries: ['/training'] })
    await waitFor(() => expect(screen.getByText(/1 deneme harcanır/i)).toBeInTheDocument())
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: /^başla$/i }))
    await waitFor(() =>
      expect(screen.getByText(/maksimum deneme sayısına ulaşıldı/i)).toBeInTheDocument(),
    )
    expect(sessionStorage.getItem('training-start-pending')).toBeNull()
  })
})

describe('Training route — already passed', () => {
  it('mount with has_passed_training=true redirects to /', async () => {
    useAuthStore.setState({
      status: 'authed',
      user: { ...FRESH_USER, has_passed_training: true },
      error: null,
    })
    server.use(mockAuthedUser({ has_seen_manual: true, has_passed_training: true }))
    renderWithProviders(<Training />, { initialEntries: ['/training'] })
    await waitFor(() => expect(screen.getByTestId('route-root')).toBeInTheDocument())
  })

  it('start returns 409 already_passed → refreshAuth + navigate /', async () => {
    const user = userEvent.setup()
    useAuthStore.setState({ status: 'authed', user: FRESH_USER, error: null })
    server.use(
      mockTrainingStartAlreadyPassed(),
      mockAuthedUser({ has_seen_manual: true, has_passed_training: true }),
    )
    renderWithProviders(<Training />, { initialEntries: ['/training'] })
    await waitFor(() => expect(screen.getByText(/1 deneme harcanır/i)).toBeInTheDocument())
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: /^başla$/i }))
    await waitFor(() => expect(screen.getByTestId('route-root')).toBeInTheDocument())
    expect(sessionStorage.getItem('training-start-pending')).toBeNull()
  })
})

describe('Training route — resume from sessionStorage', () => {
  it('F5 mid-quiz restores cached answers', async () => {
    const start = makeStartResponse()
    // Simulate persist rehydration: set the store state directly (what zustand
    // persist would restore after a real page reload from sessionStorage).
    useTrainingStore.setState({
      attemptId: start.attempt_id,
      attemptNumber: start.attempt_number,
      step: 'quiz',
      docIndex: 0,
      questions: start.questions,
      goldDocs: start.gold_docs,
      quizAnswers: { q01: 1 },
      quizResult: null,
      docRefs: { gold_a: [], gold_b: [], gold_c: [] },
      docResults: {},
      resultShown: null,
      degraded: false,
    })
    useAuthStore.setState({ status: 'authed', user: FRESH_USER, error: null })
    server.use(mockAuthedUser({ has_seen_manual: true, has_passed_training: false }))
    renderWithProviders(<Training />, { initialEntries: ['/training'] })

    await waitFor(() => expect(screen.getAllByRole('group')).toHaveLength(5))
    const radios = screen.getAllByRole('radio')
    expect(radios[1]).toHaveAttribute('aria-checked', 'true')
  })
})

describe('Training route — 409 idempotency', () => {
  it('quiz dup with cached result advances without fake breakdown', async () => {
    const user = userEvent.setup()
    const start = makeStartResponse()
    // Simulate persist rehydration with a prior quizResult already cached.
    useTrainingStore.setState({
      attemptId: 100,
      attemptNumber: 1,
      step: 'quiz',
      docIndex: 0,
      questions: start.questions,
      goldDocs: start.gold_docs,
      quizAnswers: {},
      quizResult: { score: 5, total: 5, results: [
        { question_id: 'q01', user_choice: 0, correct_choice: 0, is_correct: true },
        { question_id: 'q02', user_choice: 1, correct_choice: 1, is_correct: true },
        { question_id: 'q03', user_choice: 2, correct_choice: 2, is_correct: true },
        { question_id: 'q04', user_choice: 3, correct_choice: 3, is_correct: true },
        { question_id: 'q05', user_choice: 1, correct_choice: 1, is_correct: true },
      ] },
      docRefs: { gold_a: [], gold_b: [], gold_c: [] },
      docResults: {},
      resultShown: null,
      degraded: false,
    })
    useAuthStore.setState({ status: 'authed', user: FRESH_USER, error: null })
    server.use(
      mockAuthedUser({ has_seen_manual: true, has_passed_training: false }),
      mockQuizSubmitAlreadySubmitted(),
    )

    renderWithProviders(<Training />, { initialEntries: ['/training'] })
    await waitFor(() => expect(screen.getAllByRole('group')).toHaveLength(5))
    for (let i = 0; i < 5; i++) {
      const radios = screen.getAllByRole('radio')
      await user.click(radios[i * 4]!)
    }
    await user.click(screen.getByRole('button', { name: /cevapları gönder/i }))
    await waitFor(() => expect(screen.getByText(/5 \/ 5/)).toBeInTheDocument())
  })
})

describe('Training route — corrupt restore', () => {
  it('invalid shape wipes storage → StartScreen rendered', async () => {
    sessionStorage.setItem(
      'training-attempt-v1',
      JSON.stringify({
        state: { step: 'invalid-step', docIndex: 99 },
        version: 1,
      }),
    )
    useAuthStore.setState({ status: 'authed', user: FRESH_USER, error: null })
    server.use(mockAuthedUser({ has_seen_manual: true, has_passed_training: false }))
    renderWithProviders(<Training />, { initialEntries: ['/training'] })

    await waitFor(() => expect(screen.getByText(/1 deneme harcanır/i)).toBeInTheDocument())
  })
})

describe('Training route — pending sentinel', () => {
  it('renders PendingStartBanner when sentinel present + storage empty', async () => {
    sessionStorage.setItem('training-start-pending', JSON.stringify({ ts: Date.now() }))
    useAuthStore.setState({ status: 'authed', user: FRESH_USER, error: null })
    server.use(mockAuthedUser({ has_seen_manual: true, has_passed_training: false }))
    renderWithProviders(<Training />, { initialEntries: ['/training'] })
    await waitFor(() => expect(screen.getByText(/önceki başlatma yarıda kaldı/i)).toBeInTheDocument())
  })
})
