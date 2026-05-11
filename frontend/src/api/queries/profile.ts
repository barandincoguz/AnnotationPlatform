import { useQuery } from '@tanstack/react-query'
import { client, unwrap } from '@/api/client'
import { profileResponseSchema, type ProfileResponse } from '@/lib/profileSchemas'

export const profileKeys = {
  all: ['profile'] as const,
  me: () => [...profileKeys.all, 'me'] as const,
}

export function useProfile() {
  return useQuery<ProfileResponse>({
    queryKey: profileKeys.me(),
    queryFn: async () => {
      const raw = await unwrap(await client.GET('/api/me/profile'))
      return profileResponseSchema.parse(raw)
    },
    staleTime: 5_000,
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
  })
}
