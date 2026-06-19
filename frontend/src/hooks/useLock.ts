import { useCallback, useEffect, useRef, useState } from 'react'
import { client, ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import type { LockInfo, LockConflictDetail } from '@/api/queries/locks'

const HEARTBEAT_MS = 30_000
const HEARTBEAT_RETRY_LIMIT = 2

function releaseWithKeepalive(documentId: string) {
  try {
    const apiBase =
      typeof import.meta.env.VITE_API_BASE_URL === 'string'
        ? import.meta.env.VITE_API_BASE_URL
        : ''
    fetch(`${apiBase}/api/locks/${encodeURIComponent(documentId)}/release`, {
      method: 'POST',
      credentials: 'include',
      keepalive: true,
    }).catch(() => {
      // Server TTL is the correctness backstop.
    })
  } catch {
    // Server TTL is the correctness backstop.
  }
}

export type LockStatus =
  | 'idle'
  | 'acquiring'
  | 'held'
  | 'conflict'
  | 'lost'
  | 'error'
  | 'released'

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
  const [acquireAttempt, setAcquireAttempt] = useState(0)
  const heldRef = useRef(false)
  const heartbeatTimerRef = useRef<number | null>(null)
  const heartbeatFailuresRef = useRef(0)
  const acquireAbortRef = useRef<AbortController | null>(null)
  const effectGenerationRef = useRef(0)
  const activeEffectKeyRef = useRef('')
  const explicitlyReleasedGenerationsRef = useRef(new Set<number>())
  const myUserId = useAuthStore((s) => s.user?.id ?? null)

  useEffect(() => {
    const generation = effectGenerationRef.current + 1
    effectGenerationRef.current = generation
    const effectKey = `${docId}:${myUserId ?? 'anon'}`
    const explicitlyReleasedGenerations =
      explicitlyReleasedGenerationsRef.current
    activeEffectKeyRef.current = effectKey
    let cancelled = false
    let acquired = false

    heldRef.current = false
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
        if (cancelled || effectGenerationRef.current !== generation) {
          if (
            result.error === undefined
            && activeEffectKeyRef.current !== effectKey
          ) {
            releaseWithKeepalive(docId)
          }
          return
        }

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

        acquired = true
        heldRef.current = true
        setSnapshot({
          status: 'held',
          info: result.data,
          conflict: null,
          conflictUsername: null,
          conflictIsSameUser: false,
        })

        if (cancelled) return
        heartbeatTimerRef.current = window.setInterval(() => {
          if (cancelled || effectGenerationRef.current !== generation) return
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
            if (
              heartbeatFailuresRef.current >= HEARTBEAT_RETRY_LIMIT
              && !cancelled
              && effectGenerationRef.current === generation
            ) {
              if (heartbeatTimerRef.current !== null) {
                window.clearInterval(heartbeatTimerRef.current)
                heartbeatTimerRef.current = null
              }
              heldRef.current = false
              setSnapshot((s) => ({ ...s, status: 'lost' }))
            }
          })()
        }, HEARTBEAT_MS)
      } catch (e) {
        if (cancelled || effectGenerationRef.current !== generation) return
        if ((e as { name?: string })?.name === 'AbortError') return
        setSnapshot((s) => ({ ...s, status: 'error' }))
      }
    })()

    return () => {
      cancelled = true
      acquireAbortRef.current?.abort()
      if (heartbeatTimerRef.current !== null) {
        window.clearInterval(heartbeatTimerRef.current)
        heartbeatTimerRef.current = null
      }
      if (!acquired) return
      heldRef.current = false
      queueMicrotask(() => {
        if (explicitlyReleasedGenerations.delete(generation)) return
        const sameLogicalOwnerRestarted =
          activeEffectKeyRef.current === effectKey
          && effectGenerationRef.current !== generation
        if (!sameLogicalOwnerRestarted) releaseWithKeepalive(docId)
      })
    }
  }, [docId, myUserId, acquireAttempt])

  const release = useCallback(async () => {
    try {
      const result = await client.POST('/api/locks/{document_id}/release', {
        params: { path: { document_id: docId } },
      })
      if (result.error !== undefined) {
        throw new ApiError(
          result.response.status,
          String(result.response.status),
          'Kilit serbest bırakılamadı',
          result.error,
        )
      }
    } catch {
      throw new Error('release_failed')
    }
    if (heartbeatTimerRef.current !== null) {
      window.clearInterval(heartbeatTimerRef.current)
      heartbeatTimerRef.current = null
    }
    explicitlyReleasedGenerationsRef.current.add(effectGenerationRef.current)
    heldRef.current = false
    setSnapshot({
      status: 'released',
      info: null,
      conflict: null,
      conflictUsername: null,
      conflictIsSameUser: false,
    })
  }, [docId])

  const retry = useCallback(() => {
    setAcquireAttempt((attempt) => attempt + 1)
  }, [])

  return { ...snapshot, release, retry }
}
