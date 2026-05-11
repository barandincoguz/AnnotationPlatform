import type { QueryClient } from '@tanstack/react-query'
import { client, unwrap } from '@/api/client'
import { authKeys } from '@/api/queries/auth'
import { useAuthStore } from '@/stores/authStore'
import type { components } from '@/api/types'

type UserOut = components['schemas']['UserOut']

/**
 * Forces a fresh /api/auth/me fetch (bypassing TanStack staleness) and
 * mirrors the result into the Zustand authStore so gates re-evaluate
 * synchronously. Used after mutations that flip server-side flags.
 *
 * Spec §12.
 */
export async function refreshAuth(qc: QueryClient): Promise<UserOut> {
  const fresh = await qc.fetchQuery({
    queryKey: authKeys.me,
    queryFn: async (): Promise<UserOut> => unwrap(await client.GET('/api/auth/me')),
    staleTime: 0,
  })
  useAuthStore.getState().setUser(fresh)
  return fresh
}
