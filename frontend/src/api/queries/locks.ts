//
// Lock operations are NOT exposed as TanStack hooks — useLock (T6) manages
// acquire + heartbeat + release with AbortController + setInterval + cleanup
// patterns that don't fit useMutation. This file exports type aliases only.

import type { components } from '@/api/types'

export type LockInfo = components['schemas']['LockInfo']

export interface LockConflictDetail {
  error: 'lock_held_by_other'
  by_user_id: number
  by_username: string
  acquired_at: string
  expires_at: string
}
