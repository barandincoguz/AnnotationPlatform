import { useCallback, useEffect, useRef, useState } from 'react'
import { client, ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import type { LockInfo, LockConflictDetail } from '@/api/queries/locks'

const HEARTBEAT_MS = 30_000
const HEARTBEAT_RETRY_LIMIT = 2

export type LockStatus = 'idle' | 'acquiring' | 'held' | 'conflict' | 'lost' | 'released'

export interface LockSnapshot {
  status: LockStatus
  info: LockInfo | null
  conflict: LockConflictDetail | null
  conflictUsername: string | null
  conflictIsSameUser: boolean
}

const INITIAL: LockSnapshot = {
  status: 'idle',
  info: null,
  conflict: null,
  conflictUsername: null,
  conflictIsSameUser: false,
}

export function useLock(docId: string) {
  const [snapshot, setSnapshot] = useState<LockSnapshot>(INITIAL)
  const cancelledRef = useRef(false)
  const heartbeatTimerRef = useRef<number | null>(null)
  const heartbeatFailuresRef = useRef(0)
  const acquireAbortRef = useRef<AbortController | null>(null)
  const myUserId = useAuthStore((s) => s.user?.id ?? null)

  useEffect(() => {
    cancelledRef.current = false
    heartbeatFailuresRef.current = 0
    const acquireCtrl = new AbortController()
    acquireAbortRef.current = acquireCtrl
    setSnapshot((s) => ({ ...s, status: 'acquiring' }))

    void (async () => {
      try {
        const result = await client.POST('/api/locks/{document_id}/acquire', {
          params: { path: { document_id: docId } },
          signal: acquireCtrl.signal,
        })
        if (cancelledRef.current) return

        if (result.error !== undefined) {
          if (result.response.status === 409) {
            const detail = (result.error as { detail?: LockConflictDetail }).detail ?? null
            const same = detail?.by_user_id === myUserId
            setSnapshot({
              status: 'conflict',
              info: null,
              conflict: detail,
              conflictUsername: detail?.by_username ?? null,
              conflictIsSameUser: same,
            })
            return
          }
          throw new ApiError(
            result.response.status,
            String(result.response.status),
            'Kilit alınamadı',
            result.error,
          )
        }

        if (cancelledRef.current) return
        setSnapshot({
          status: 'held',
          info: result.data,
          conflict: null,
          conflictUsername: null,
          conflictIsSameUser: false,
        })

        if (cancelledRef.current) return
        heartbeatTimerRef.current = window.setInterval(() => {
          if (cancelledRef.current) return
          void (async () => {
            try {
              const hb = await client.POST('/api/locks/{document_id}/heartbeat', {
                params: { path: { document_id: docId } },
              })
              if (hb.error !== undefined) {
                if (hb.response.status === 404) {
                  heartbeatFailuresRef.current = HEARTBEAT_RETRY_LIMIT
                } else {
                  heartbeatFailuresRef.current += 1
                }
              } else {
                heartbeatFailuresRef.current = 0
              }
            } catch {
              heartbeatFailuresRef.current += 1
            }
            if (heartbeatFailuresRef.current >= HEARTBEAT_RETRY_LIMIT && !cancelledRef.current) {
              if (heartbeatTimerRef.current !== null) {
                window.clearInterval(heartbeatTimerRef.current)
                heartbeatTimerRef.current = null
              }
              setSnapshot((s) => ({ ...s, status: 'lost' }))
            }
          })()
        }, HEARTBEAT_MS)
      } catch (e) {
        if (cancelledRef.current) return
        if ((e as { name?: string })?.name === 'AbortError') return
        setSnapshot((s) => ({ ...s, status: 'idle' }))
      }
    })()

    return () => {
      cancelledRef.current = true
      acquireAbortRef.current?.abort()
      if (heartbeatTimerRef.current !== null) {
        window.clearInterval(heartbeatTimerRef.current)
        heartbeatTimerRef.current = null
      }
      try {
        // Best-effort fire-and-forget release on cleanup (page close, route
        // change). Uses keepalive so the browser will deliver it even if the
        // tab is closing. 90s server TTL is the correctness backstop if this
        // never lands. Errors are intentionally swallowed.
        // Build absolute URL so MSW (jsdom tests) matches reliably and any
        // misconfigured baseURL in prod still works.
        const origin = typeof window !== 'undefined' ? window.location.origin : ''
        fetch(`${origin}/api/locks/${encodeURIComponent(docId)}/release`, {
          method: 'POST',
          credentials: 'include',
          keepalive: true,
        }).catch(() => {
          // swallow — server TTL is the backstop
        })
      } catch {
        // no-op
      }
    }
  }, [docId, myUserId])

  const release = useCallback(async () => {
    if (heartbeatTimerRef.current !== null) {
      window.clearInterval(heartbeatTimerRef.current)
      heartbeatTimerRef.current = null
    }
    try {
      await client.POST('/api/locks/{document_id}/release', {
        params: { path: { document_id: docId } },
      })
    } catch {
      throw new Error('release_failed')
    }
    setSnapshot({
      status: 'released',
      info: null,
      conflict: null,
      conflictUsername: null,
      conflictIsSameUser: false,
    })
  }, [docId])

  return { ...snapshot, release }
}
