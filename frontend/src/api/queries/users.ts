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
    // Codex BROKEN-D: SSE drops can leave indefinite stale state.
    refetchInterval: 30_000,
  })
}
