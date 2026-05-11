import { useMutation } from '@tanstack/react-query'
import { client, unwrapVoid } from '@/api/client'

export function useSeenManualMutation() {
  return useMutation({
    mutationFn: async () => unwrapVoid(await client.POST('/api/me/seen-manual')),
  })
}
