import { create } from 'zustand'

interface PlaceholderState {
  quizResult: { score: number; total: number } | null
  docResults: Record<string, { passed: boolean; matched_count: number; expected_count: number; min_concept_count: number }>
  degraded: boolean
  step: string
  clear: () => void
}

export const useTrainingStore = create<PlaceholderState>((set) => ({
  quizResult: null,
  docResults: {},
  degraded: false,
  step: 'idle',
  clear: () => set({ quizResult: null, docResults: {}, degraded: false, step: 'idle' }),
}))
