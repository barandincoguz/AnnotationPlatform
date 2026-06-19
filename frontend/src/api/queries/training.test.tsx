import { describe, it, expect } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import {
  mockTrainingStartLockedOut,
  mockTrainingStartAlreadyPassed,
  mockQuizSubmitAlreadySubmitted,
} from '@/test/msw-handlers'
import { server } from '@/test/msw-server'
import {
  useTrainingStartMutation,
  useQuizSubmitMutation,
  useAnnotateSubmitMutation,
} from './training'

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
  Wrapper.displayName = 'TestWrapper'
  return Wrapper
}

describe('useTrainingStartMutation', () => {
  it('returns parsed StartResponse on success', async () => {
    const { result } = renderHook(() => useTrainingStartMutation(), { wrapper: createWrapper() })
    const data = await result.current.mutateAsync()
    expect(data.questions).toHaveLength(5)
    expect(data.gold_docs).toHaveLength(3)
    expect(typeof data.attempt_id).toBe('number')
  })

  it('writes pending-start sentinel before request', async () => {
    sessionStorage.removeItem('training-start-pending')
    const { result } = renderHook(() => useTrainingStartMutation(), { wrapper: createWrapper() })
    const promise = result.current.mutateAsync()
    await waitFor(() => expect(sessionStorage.getItem('training-start-pending')).not.toBeNull())
    await promise
  })

  it('throws ApiError on 403 locked out', async () => {
    server.use(mockTrainingStartLockedOut())
    const { result } = renderHook(() => useTrainingStartMutation(), { wrapper: createWrapper() })
    await expect(result.current.mutateAsync()).rejects.toMatchObject({
      status: 403,
      code: 'max_attempts_reached',
    })
  })

  it('throws ApiError on 409 already_passed', async () => {
    server.use(mockTrainingStartAlreadyPassed())
    const { result } = renderHook(() => useTrainingStartMutation(), { wrapper: createWrapper() })
    await expect(result.current.mutateAsync()).rejects.toMatchObject({
      status: 409,
      code: 'already_passed',
    })
  })
})

describe('useQuizSubmitMutation', () => {
  it('returns parsed result on success', async () => {
    const { result } = renderHook(() => useQuizSubmitMutation(), { wrapper: createWrapper() })
    const data = await result.current.mutateAsync({ attempt_id: 1, answers: { q01: 0 } })
    expect(data.score).toBe(4)
    expect(data.total).toBe(5)
    expect(data.results).toHaveLength(5)
  })

  it('throws ApiError on 409', async () => {
    server.use(mockQuizSubmitAlreadySubmitted())
    const { result } = renderHook(() => useQuizSubmitMutation(), { wrapper: createWrapper() })
    await expect(result.current.mutateAsync({ attempt_id: 1, answers: {} })).rejects.toMatchObject({
      status: 409,
      code: 'quiz_already_submitted',
    })
  })
})

describe('useAnnotateSubmitMutation', () => {
  it('returns parsed result on success', async () => {
    const { result } = renderHook(() => useAnnotateSubmitMutation(), { wrapper: createWrapper() })
    const data = await result.current.mutateAsync({
      attempt_id: 1,
      gold_id: 'gold_a',
      references: [],
    })
    expect(data).toMatchObject({ passed: true, matched_count: 2 })
  })
})
