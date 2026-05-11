import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { client, unwrap, unwrapVoid } from '@/api/client'
import { refreshAuth } from '@/lib/refreshAuth'
import {
  startResponseSchema,
  quizSubmitResponseSchema,
  annotateSubmitResponseSchema,
  type StartResponse,
  type QuizSubmitResponse,
  type AnnotateSubmitResponse,
} from '@/lib/trainingSchemas'
import type { components } from '@/api/types'

type ReferenceItem = components['schemas']['ReferenceItem']

export const trainingKeys = { all: ['training'] as const }
export const PENDING_START_SENTINEL_KEY = 'training-start-pending'

export function useTrainingStartMutation() {
  return useMutation<StartResponse, Error, void>({
    mutationFn: async () => {
      sessionStorage.setItem(PENDING_START_SENTINEL_KEY, JSON.stringify({ ts: Date.now() }))
      const raw = await unwrap(await client.GET('/api/training/start'))
      return startResponseSchema.parse(raw)
    },
  })
}

export function useQuizSubmitMutation() {
  return useMutation<
    QuizSubmitResponse,
    Error,
    { attempt_id: number; answers: Record<string, number> }
  >({
    mutationFn: async (body) => {
      const raw = await unwrap(await client.POST('/api/training/quiz/submit', { body }))
      return quizSubmitResponseSchema.parse(raw)
    },
  })
}

export function useAnnotateSubmitMutation() {
  return useMutation<
    AnnotateSubmitResponse,
    Error,
    { attempt_id: number; gold_id: string; references: ReferenceItem[] }
  >({
    mutationFn: async (body) => {
      const raw = await unwrap(await client.POST('/api/training/annotate/submit', { body }))
      return annotateSubmitResponseSchema.parse(raw)
    },
  })
}

/**
 * 16c.1: bypass the training gate. POSTs /api/training/skip, awaits
 * refreshAuth to pull the new has_passed_training=1 into the auth
 * store, invalidates all queries so the gate re-evaluates, then
 * navigates to /. Error path: toast.error and stay put.
 */
export function useSkipTrainingMutation() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  return useMutation({
    mutationFn: async () =>
      unwrapVoid(await client.POST('/api/training/skip')),
    onSuccess: async () => {
      await refreshAuth(qc)
      void qc.invalidateQueries()
      toast.warning('Eğitim atlandı. İyi şanslar.', { duration: 5_000 })
      navigate('/', { replace: true })
    },
    onError: () => {
      toast.error('Eğitim atlanamadı. Lütfen tekrar dene.')
    },
  })
}
