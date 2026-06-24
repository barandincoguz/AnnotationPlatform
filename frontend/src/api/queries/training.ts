import { useMutation } from '@tanstack/react-query'
import { client, unwrap } from '@/api/client'
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
      const raw = await unwrap(await client.POST('/api/training/start'))
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

export function useTrainingSkipMutation() {
  return useMutation<{ ok: boolean }, Error, void>({
    mutationFn: async () => {
      const raw = await unwrap(await client.POST('/api/training/skip'))
      return raw
    },
  })
}
