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
    // Profile data (XP, streak, daily target, badges) doesn't change
    // every few seconds; SSE invalidates on real mutations
    // (`activity_seen`, `badge_unlocked`). Drop refetchOnWindowFocus
    // here — the prior config triggered a 3-fetch thunder on every
    // tab-return (profile + online_users + notifications). Reconnect
    // refetch is kept; it's the actual "we may have missed an event"
    // signal.
    staleTime: 30_000,
    refetchOnReconnect: true,
  })
}
