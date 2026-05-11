import { useQuery } from '@tanstack/react-query'
import { client, unwrap } from '@/api/client'
import { helpResponseSchema, type HelpResponse } from '@/lib/trainingSchemas'

export const helpKeys = {
  all: ['help'] as const,
  sections: () => [...helpKeys.all, 'sections'] as const,
}

export function useHelpQuery() {
  return useQuery<HelpResponse>({
    queryKey: helpKeys.sections(),
    queryFn: async () => {
      const raw = await unwrap(await client.GET('/api/help'))
      return helpResponseSchema.parse(raw)
    },
    staleTime: Infinity,
  })
}
