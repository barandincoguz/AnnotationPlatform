import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { ApiError } from '@/api/client'
import { useTrainingStore } from '@/stores/trainingStore'
import { submitWithRecovery, AbortAdvance } from './trainingRecovery'

const makeQc = () => new QueryClient({ defaultOptions: { queries: { retry: false } } })

describe('submitWithRecovery', () => {
  beforeEach(() => {
    useTrainingStore.getState().clear()
  })

  it('passes through 200 result unchanged', async () => {
    const qc = makeQc()
    const result = await submitWithRecovery({
      submit: async () => ({ score: 3, total: 5 }),
      key: { kind: 'quiz' },
      qc,
    })
    expect(result).toEqual({ score: 3, total: 5 })
  })

  it('on 409 quiz with cached prior result, returns the cache', async () => {
    const qc = makeQc()
    useTrainingStore.setState({ quizResult: { score: 4, total: 5 } })
    const result = await submitWithRecovery({
      submit: async () => {
        throw new ApiError(409, 'quiz_already_submitted', 'dup')
      },
      key: { kind: 'quiz' },
      qc,
    })
    expect(result).toEqual({ score: 4, total: 5 })
  })

  it('on 409 quiz WITHOUT cached prior, throws AbortAdvance + DEGRADED', async () => {
    const qc = makeQc()
    const fetchSpy = vi.spyOn(qc, 'fetchQuery').mockResolvedValue({
      id: 1,
      username: 'tester',
      role: 'user',
      avatar_color: '#000',
      has_seen_manual: true,
      has_passed_training: true,
    } as never)

    await expect(
      submitWithRecovery({
        submit: async () => {
          throw new ApiError(409, 'quiz_already_submitted', 'dup')
        },
        key: { kind: 'quiz' },
        qc,
      }),
    ).rejects.toBeInstanceOf(AbortAdvance)

    expect(fetchSpy).toHaveBeenCalled()
    expect(useTrainingStore.getState().degraded).toBe(true)
    expect(useTrainingStore.getState().step).toBe('summary')
  })

  it('on 409 doc with cached prior result, returns the cache', async () => {
    const qc = makeQc()
    const docResult = {
      passed: true,
      matched_count: 2,
      expected_count: 2,
      min_concept_count: 1,
    }
    useTrainingStore.setState({ docResults: { gold_x: docResult } })
    const result = await submitWithRecovery({
      submit: async () => {
        throw new ApiError(409, 'gold_doc_already_submitted', 'dup')
      },
      key: { kind: 'doc', goldId: 'gold_x' },
      qc,
    })
    expect(result).toEqual(docResult)
  })

  it('on non-409 error, rethrows', async () => {
    const qc = makeQc()
    await expect(
      submitWithRecovery({
        submit: async () => {
          throw new ApiError(500, 'boom', 'server')
        },
        key: { kind: 'quiz' },
        qc,
      }),
    ).rejects.toMatchObject({ status: 500 })
  })
})
