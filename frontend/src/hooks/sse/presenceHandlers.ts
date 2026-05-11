import type { QueryClient } from '@tanstack/react-query'
import {
  userOnlinePayloadSchema, userOfflinePayloadSchema, parseEventData,
} from '@/lib/sseSchemas'
import { usersKeys } from '@/api/queries/users'

interface PresenceHandlerOpts {
  qc: QueryClient
}

export function registerPresenceHandlers(
  es: EventSource, opts: PresenceHandlerOpts,
) {
  es.addEventListener('user_online', (e) => {
    const data = parseEventData(e, userOnlinePayloadSchema)
    if (!data) return
    void opts.qc.invalidateQueries({ queryKey: usersKeys.online() })
  })

  es.addEventListener('user_offline', (e) => {
    const data = parseEventData(e, userOfflinePayloadSchema)
    if (!data) return
    void opts.qc.invalidateQueries({ queryKey: usersKeys.online() })
  })
}
