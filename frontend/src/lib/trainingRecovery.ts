import type { QueryClient } from '@tanstack/react-query'
import { useTrainingStore } from '@/stores/trainingStore'
import { isApiError, is409AlreadySubmittedQuiz, is409AlreadySubmittedDoc } from './apiError'
import { refreshAuth } from './refreshAuth'

/**
 * Recovery signal: the caller MUST NOT call store.advance* after this is
 * thrown. The recovery path has already transitioned to the summary step.
 */
export class AbortAdvance extends Error {
  constructor() {
    super('caller should not advance; recovery has redirected')
    this.name = 'AbortAdvance'
  }
}

export type RecoveryKey = { kind: 'quiz' } | { kind: 'doc'; goldId: string }

interface SubmitWithRecoveryArgs<R> {
  submit: () => Promise<R>
  key: RecoveryKey
  qc: QueryClient
}

/**
 * Wraps a submit mutation with idempotency-aware recovery.
 *
 * - 200 → return result, caller advances
 * - 409 already_submitted + cached prior result in store → return cached, caller advances
 * - 409 already_submitted + no cached prior → DEGRADED: refreshAuth + step='summary' + throw AbortAdvance
 * - other errors → rethrow
 *
 * Spec §8.6.
 */
export async function submitWithRecovery<R>(args: SubmitWithRecoveryArgs<R>): Promise<R> {
  try {
    return await args.submit()
  } catch (err) {
    if (!isApiError(err)) throw err

    const store = useTrainingStore.getState()

    if (args.key.kind === 'quiz' && is409AlreadySubmittedQuiz(err)) {
      const cached = store.quizResult
      if (cached) return cached as unknown as R
      await refreshAuth(args.qc)
      useTrainingStore.setState({ degraded: true, step: 'summary' })
      throw new AbortAdvance()
    }

    if (args.key.kind === 'doc' && is409AlreadySubmittedDoc(err)) {
      const cached = store.docResults[args.key.goldId]
      if (cached) return cached as unknown as R
      await refreshAuth(args.qc)
      useTrainingStore.setState({ degraded: true, step: 'summary' })
      throw new AbortAdvance()
    }

    throw err
  }
}
