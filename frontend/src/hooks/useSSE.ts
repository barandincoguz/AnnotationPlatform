import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useAuthStore } from '@/stores/authStore'

interface UseSSEOpts {
  acquiringDocId: string | null
}

const DOC_PATH_RE = /^\/docs\/([^/?#]+)/

function getCurrentDocIdFromUrl(): string | null {
  const m = DOC_PATH_RE.exec(window.location.pathname)
  return m?.[1] ?? null
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

    es.addEventListener('lock_acquired', (e) => {
      if (cancelled) return
      const raw = (e as MessageEvent<string>).data
      let data: {
        document_id: string
        by_user_id: number
        by_username: string
      }
      try {
        data = JSON.parse(raw) as typeof data
      } catch {
        return
      }
      void qc.invalidateQueries({ queryKey: ['feed'] })
      if (data.document_id === acquiringRef.current) return
      if (data.by_user_id === meId) return
      const currentDocId = getCurrentDocIdFromUrl()
      if (data.document_id === currentDocId) {
        toast.error(`Bu doküman ${data.by_username} tarafından alındı.`)
        navigate('/', { replace: true })
      }
    })

    es.addEventListener('lock_released', () => {
      if (cancelled) return
      void qc.invalidateQueries({ queryKey: ['feed'] })
    })

    es.onerror = () => {
      if (cancelled) return
      if (es.readyState === EventSource.CONNECTING) {
        void qc.invalidateQueries({ queryKey: ['feed'] })
      }
    }

    return () => {
      cancelled = true
      es.close()
    }
  }, [qc, navigate, meId])
}
