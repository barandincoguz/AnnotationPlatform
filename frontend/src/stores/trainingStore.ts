import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import type {
  StartResponse,
  Question,
  GoldDoc,
  QuizSubmitResponse,
  AnnotateSubmitResponse,
} from '@/lib/trainingSchemas'
import type { components } from '@/api/types'

type ReferenceDraft = components['schemas']['ReferenceItem']

export type TrainingStep = 'idle' | 'quiz' | 'doc' | 'summary' | 'locked-out'

export interface TrainingState {
  attemptId: number | null
  attemptNumber: number | null
  step: TrainingStep
  docIndex: 0 | 1 | 2
  questions: Question[]
  goldDocs: GoldDoc[]
  quizAnswers: Record<string, number>
  quizResult: QuizSubmitResponse | null
  docRefs: Record<string, ReferenceDraft[]>
  docResults: Record<string, AnnotateSubmitResponse>
  resultShown: { kind: 'quiz' } | { kind: 'doc'; goldId: string } | null
  degraded: boolean
}

export interface TrainingActions {
  hydrate: (start: StartResponse) => void
  setQuizAnswer: (questionId: string, choice: number) => void
  recordQuizResult: (r: QuizSubmitResponse) => void
  setDocRefs: (goldId: string, refs: ReferenceDraft[]) => void
  recordDocResult: (goldId: string, r: AnnotateSubmitResponse) => void
  advanceDoc: () => void
  setStep: (step: TrainingStep) => void
  markDegraded: () => void
  clear: () => void
}

const initialState: TrainingState = {
  attemptId: null,
  attemptNumber: null,
  step: 'idle',
  docIndex: 0,
  questions: [],
  goldDocs: [],
  quizAnswers: {},
  quizResult: null,
  docRefs: {},
  docResults: {},
  resultShown: null,
  degraded: false,
}

const STORAGE_KEY = 'training-attempt-v1'

export function validateRestoredShape(s: Partial<TrainingState>): boolean {
  if (s.attemptId !== null && s.attemptId !== undefined && typeof s.attemptId !== 'number') return false
  if (typeof s.step !== 'string') return false
  if (!['idle', 'quiz', 'doc', 'summary', 'locked-out'].includes(s.step)) return false
  if (![0, 1, 2].includes(s.docIndex as number)) return false
  if (s.step === 'quiz' || s.step === 'doc' || s.step === 'summary') {
    if (!Array.isArray(s.questions) || s.questions.length !== 5) return false
    if (!Array.isArray(s.goldDocs) || s.goldDocs.length !== 3) return false
    if (typeof s.attemptId !== 'number') return false
  }
  return true
}

export const useTrainingStore = create<TrainingState & TrainingActions>()(
  persist(
    (set) => ({
      ...initialState,
      hydrate: (s) =>
        set({
          attemptId: s.attempt_id,
          attemptNumber: s.attempt_number,
          step: 'quiz',
          docIndex: 0,
          questions: s.questions,
          goldDocs: s.gold_docs,
          quizAnswers: {},
          quizResult: null,
          docRefs: Object.fromEntries(s.gold_docs.map((d) => [d.gold_id, []])),
          docResults: {},
          resultShown: null,
          degraded: false,
        }),
      setQuizAnswer: (questionId, choice) =>
        set((prev) => ({ quizAnswers: { ...prev.quizAnswers, [questionId]: choice } })),
      recordQuizResult: (r) => set({ quizResult: r, resultShown: { kind: 'quiz' } }),
      setDocRefs: (goldId, refs) =>
        set((prev) => ({ docRefs: { ...prev.docRefs, [goldId]: refs } })),
      recordDocResult: (goldId, r) =>
        set((prev) => ({
          docResults: { ...prev.docResults, [goldId]: r },
          resultShown: { kind: 'doc', goldId },
        })),
      advanceDoc: () =>
        set((prev) => {
          if (prev.docIndex < 2) {
            return { docIndex: (prev.docIndex + 1) as 0 | 1 | 2, resultShown: null }
          }
          return { resultShown: null }
        }),
      setStep: (step) => set({ step, resultShown: null }),
      markDegraded: () => set({ degraded: true }),
      clear: () => {
        set({ ...initialState })
        sessionStorage.removeItem(STORAGE_KEY)
      },
    }),
    {
      name: STORAGE_KEY,
      storage: createJSONStorage(() => sessionStorage),
      version: 1,
      partialize: (s) => ({
        attemptId: s.attemptId,
        attemptNumber: s.attemptNumber,
        step: s.step,
        docIndex: s.docIndex,
        questions: s.questions,
        goldDocs: s.goldDocs,
        quizAnswers: s.quizAnswers,
        quizResult: s.quizResult,
        docRefs: s.docRefs,
        docResults: s.docResults,
        resultShown: s.resultShown,
        degraded: s.degraded,
      }),
      migrate: (oldState, oldVersion) => {
        if (oldVersion < 1) return undefined
        return oldState
      },
      onRehydrateStorage: () => (state, error) => {
        if (error || !state) return
        if (!validateRestoredShape(state)) {
          sessionStorage.removeItem(STORAGE_KEY)
          useTrainingStore.setState({ ...initialState })
        }
      },
    },
  ),
)
