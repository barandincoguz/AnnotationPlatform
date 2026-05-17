import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/stores/authStore'
import { registerLockHandlers } from './sse/lockHandlers'
import { registerFeedHandlers } from './sse/feedHandlers'
import { registerNotificationHandlers } from './sse/notificationHandlers'
import { registerPresenceHandlers } from './sse/presenceHandlers'
import { usersKeys } from '@/api/queries/users'
import { feedKeys } from '@/api/queries/feed'

interface UseSSEOpts {
  acquiringDocId: string | null
}

export function useSSE(opts: UseSSEOpts) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const meId = useAuthStore((s) => s.user?.id ?? null)
  const acquiringRef = useRef<string | null>(opts.acquiringDocId)
  acquiringRef.current = opts.acquiringDocId

  useEffect(() => {
    let cancelled = false
    const es = new EventSource('/api/events')

    registerLockHandlers(es, { qc, navigate, meId, acquiringRef })
    registerFeedHandlers(es, { qc })
    registerNotificationHandlers(es, { qc })
    registerPresenceHandlers(es, { qc })

    es.onerror = () => {
      if (cancelled) return
      if (es.readyState === EventSource.CONNECTING) {
        // 16d: reconcile feed AND online roster on flaky links.
        void qc.invalidateQueries({ queryKey: feedKeys.all })
        void qc.invalidateQueries({ queryKey: usersKeys.online() })
      }
    }

    return () => {
      cancelled = true
      es.close()
    }
  }, [qc, navigate, meId])
}
