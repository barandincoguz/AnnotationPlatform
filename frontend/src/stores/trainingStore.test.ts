import { describe, it, expect, beforeEach } from 'vitest'
import { useTrainingStore } from './trainingStore'
import type { StartResponse } from '@/lib/trainingSchemas'

const makeStart = (): StartResponse => ({
  attempt_id: 42,
  attempt_number: 1,
  questions: Array.from({ length: 5 }, (_, i) => ({
    id: `q${i + 1}`,
    text: `Soru ${i + 1}`,
    choices: ['a', 'b', 'c', 'd'],
  })),
  gold_docs: [
    { gold_id: 'gold_a', content: 'A', expected_concepts: [], min_concept_count: 1 },
    { gold_id: 'gold_b', content: 'B', expected_concepts: [], min_concept_count: 1 },
    { gold_id: 'gold_c', content: 'C', expected_concepts: [], min_concept_count: 1 },
  ],
})

describe('trainingStore', () => {
  beforeEach(() => {
    sessionStorage.clear()
    useTrainingStore.getState().clear()
  })

  it('initial state is idle', () => {
    const s = useTrainingStore.getState()
    expect(s.step).toBe('idle')
    expect(s.attemptId).toBeNull()
    expect(s.docIndex).toBe(0)
    expect(s.degraded).toBe(false)
  })

  it('hydrate transitions to quiz', () => {
    useTrainingStore.getState().hydrate(makeStart())
    const s = useTrainingStore.getState()
    expect(s.step).toBe('quiz')
    expect(s.attemptId).toBe(42)
    expect(s.questions).toHaveLength(5)
    expect(s.goldDocs).toHaveLength(3)
    expect(s.docRefs).toEqual({ gold_a: [], gold_b: [], gold_c: [] })
  })

  it('setQuizAnswer accumulates answers', () => {
    useTrainingStore.getState().hydrate(makeStart())
    useTrainingStore.getState().setQuizAnswer('q1', 2)
    useTrainingStore.getState().setQuizAnswer('q2', 0)
    expect(useTrainingStore.getState().quizAnswers).toEqual({ q1: 2, q2: 0 })
  })

  it('recordQuizResult sets resultShown to quiz', () => {
    useTrainingStore.getState().hydrate(makeStart())
    useTrainingStore.getState().recordQuizResult({ score: 4, total: 5 })
    const s = useTrainingStore.getState()
    expect(s.quizResult).toEqual({ score: 4, total: 5 })
    expect(s.resultShown).toEqual({ kind: 'quiz' })
  })

  it('setDocRefs persists refs by gold_id', () => {
    useTrainingStore.getState().hydrate(makeStart())
    const refs = [{ kanun_no: '5520', kanun_ad: null, madde: '5', fikra: '1', bent: 'a', source_text: 'x' }]
    useTrainingStore.getState().setDocRefs('gold_a', refs)
    expect(useTrainingStore.getState().docRefs.gold_a).toEqual(refs)
  })

  it('recordDocResult sets resultShown to doc', () => {
    useTrainingStore.getState().hydrate(makeStart())
    useTrainingStore.getState().recordDocResult('gold_a', {
      passed: true, matched_count: 2, expected_count: 2, min_concept_count: 1,
    })
    const s = useTrainingStore.getState()
    expect(s.docResults.gold_a!.passed).toBe(true)
    expect(s.resultShown).toEqual({ kind: 'doc', goldId: 'gold_a' })
  })

  it('advanceDoc 0→1', () => {
    useTrainingStore.getState().hydrate(makeStart())
    useTrainingStore.getState().advanceDoc()
    expect(useTrainingStore.getState().docIndex).toBe(1)
    expect(useTrainingStore.getState().resultShown).toBeNull()
  })

  it('clear wipes storage and resets to initial', () => {
    useTrainingStore.getState().hydrate(makeStart())
    expect(useTrainingStore.getState().step).toBe('quiz')
    useTrainingStore.getState().clear()
    expect(useTrainingStore.getState().step).toBe('idle')
    expect(sessionStorage.getItem('training-attempt-v1')).toBeNull()
  })

  it('persist roundtrip — write preserves state', () => {
    useTrainingStore.getState().hydrate(makeStart())
    useTrainingStore.getState().setQuizAnswer('q1', 2)
    const raw = sessionStorage.getItem('training-attempt-v1')
    expect(raw).not.toBeNull()
    const parsed = JSON.parse(raw!) as { state: { step: string; quizAnswers: Record<string, number> } }
    expect(parsed.state.step).toBe('quiz')
    expect(parsed.state.quizAnswers.q1).toBe(2)
  })

  it('markDegraded sets flag', () => {
    useTrainingStore.getState().hydrate(makeStart())
    useTrainingStore.getState().markDegraded()
    expect(useTrainingStore.getState().degraded).toBe(true)
  })

  it('setStep changes step and clears resultShown', () => {
    useTrainingStore.getState().hydrate(makeStart())
    useTrainingStore.setState({ resultShown: { kind: 'quiz' } })
    useTrainingStore.getState().setStep('doc')
    expect(useTrainingStore.getState().step).toBe('doc')
    expect(useTrainingStore.getState().resultShown).toBeNull()
  })
})
