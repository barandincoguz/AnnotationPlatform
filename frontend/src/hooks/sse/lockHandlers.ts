import type { QueryClient } from '@tanstack/react-query'
import type { MutableRefObject } from 'react'
import { toast as defaultToast } from 'sonner'
import type { NavigateFunction } from 'react-router-dom'

interface LockHandlerOpts {
  qc: QueryClient
  navigate: NavigateFunction
  meId: number | null
  acquiringRef: MutableRefObject<string | null>
  /** Injectable for tests — default is sonner's toast singleton. */
  toast?: typeof defaultToast
}

const DOC_PATH_RE = /^\/docs\/([^/?#]+)/

function getCurrentDocIdFromUrl(): string | null {
  const m = DOC_PATH_RE.exec(window.location.pathname)
  return m?.[1] ?? null
}

export function registerLockHandlers(es: EventSource, opts: LockHandlerOpts) {
  const t = opts.toast ?? defaultToast

  es.addEventListener('lock_acquired', (e) => {
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
    void opts.qc.invalidateQueries({ queryKey: ['feed'] })
    if (data.document_id === opts.acquiringRef.current) return
    if (data.by_user_id === opts.meId) return
    const currentDocId = getCurrentDocIdFromUrl()
    if (data.document_id === currentDocId) {
      t.error(`Bu doküman ${data.by_username} tarafından alındı.`)
      opts.navigate('/', { replace: true })
    }
  })

  es.addEventListener('lock_released', () => {
    void opts.qc.invalidateQueries({ queryKey: ['feed'] })
  })
}
