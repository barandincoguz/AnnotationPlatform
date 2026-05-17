import { useQuery } from '@tanstack/react-query'
import { client, unwrap } from '@/api/client'
import { onlineUsersSchema, type OnlineUsers } from '@/lib/profileSchemas'

export const usersKeys = {
  all: ['users'] as const,
  online: () => [...usersKeys.all, 'online'] as const,
}

export function useOnlineUsers() {
  return useQuery<OnlineUsers>({
    queryKey: usersKeys.online(),
    queryFn: async () => {
      const raw = await unwrap(await client.GET('/api/users/online'))
      return onlineUsersSchema.parse(raw)
    },
    staleTime: 30_000,
    // SSE invalidates this query on `user_online`/`user_offline`
    // events, so polling is belt-and-suspenders against SSE drops.
    // Bumped 30s → 60s to halve the idle baseline; the existing
    // SSE reconnect path still refetches immediately when the
    // channel comes back, so a real drop is bounded by that round-trip.
    refetchInterval: 60_000,
  })
}
