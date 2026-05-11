import type { QueryClient } from '@tanstack/react-query'

interface FeedHandlerOpts {
  qc: QueryClient
}

export function registerFeedHandlers(es: EventSource, opts: FeedHandlerOpts) {
  es.addEventListener('annotation_saved', (e) => {
    const raw = (e as MessageEvent<string>).data
    try {
      JSON.parse(raw)
    } catch {
      return
    }
    void opts.qc.invalidateQueries({ queryKey: ['feed'] })
  })
}
