import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { client, unwrap } from '@/api/client'
import {
  feedbackListResponseSchema,
  feedbackRowSchema,
  type FeedbackCreateRequest,
  type FeedbackRow,
  type FeedbackType,
} from '@/lib/feedbackSchemas'

export const feedbackKeys = {
  all: ['feedback'] as const,
  list: (typeFilter: FeedbackType | 'all') => [...feedbackKeys.all, 'list', typeFilter] as const,
}

export function useFeedbackList(typeFilter?: FeedbackType) {
  return useQuery<FeedbackRow[]>({
    queryKey: feedbackKeys.list(typeFilter ?? 'all'),
    queryFn: async () => {
      const result = typeFilter
        ? await client.GET('/api/admin/feedback', {
            params: { query: { type_filter: typeFilter } },
          })
        : await client.GET('/api/admin/feedback')
      const raw = await unwrap(result)
      return feedbackListResponseSchema.parse(raw)
    },
  })
}

export function useSubmitFeedbackMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: FeedbackCreateRequest) => {
      const raw = await unwrap(await client.POST('/api/feedback', { body: payload }))
      return feedbackRowSchema.parse(raw)
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: feedbackKeys.all })
    },
  })
}

