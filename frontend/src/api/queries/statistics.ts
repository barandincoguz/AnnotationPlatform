import { useQuery } from '@tanstack/react-query'
import { client, unwrap } from '@/api/client'
import { statisticsResponseSchema, type StatisticsResponse } from '@/lib/statisticsSchemas'

export const statisticsKeys = {
  all: ['statistics'] as const,
  users: () => [...statisticsKeys.all, 'users'] as const,
}

export function useUserStatistics() {
  return useQuery<StatisticsResponse>({
    queryKey: statisticsKeys.users(),
    queryFn: async () => {
      const raw = await unwrap(await client.GET('/api/statistics/users'))
      return statisticsResponseSchema.parse(raw)
    },
    staleTime: 30_000,
  })
}
