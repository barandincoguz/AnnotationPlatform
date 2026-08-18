import { useQuery } from '@tanstack/react-query'
import { z } from 'zod'
import { client, unwrap } from '@/api/client'
import { helpResponseSchema, type HelpResponse } from '@/lib/trainingSchemas'

export const helpKeys = {
  all: ['help'] as const,
  sections: () => [...helpKeys.all, 'sections'] as const,
  lawAbbreviations: () => [...helpKeys.all, 'law-abbreviations'] as const,
}

export const lawAbbreviationSchema = z.object({
  name: z.string(),
  number: z.string().nullable(),
  abbrevs: z.array(z.string()),
})
export const lawAbbreviationsResponseSchema = z.object({
  laws: z.array(lawAbbreviationSchema),
})
export type LawAbbreviation = z.infer<typeof lawAbbreviationSchema>
export type LawAbbreviationsResponse = z.infer<typeof lawAbbreviationsResponseSchema>

export function useLawAbbreviationsQuery() {
  return useQuery<LawAbbreviationsResponse>({
    queryKey: helpKeys.lawAbbreviations(),
    queryFn: async () => {
      const raw = await unwrap(await client.GET('/api/law-abbreviations'))
      return lawAbbreviationsResponseSchema.parse(raw)
    },
    staleTime: Infinity,
  })
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
