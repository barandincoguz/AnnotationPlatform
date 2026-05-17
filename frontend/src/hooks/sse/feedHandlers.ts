import type { QueryClient } from '@tanstack/react-query'

interface FeedHandlerOpts {
  qc: QueryClient
}

// Both `annotation_saved` and `annotation_completed` move a doc between
// feed tabs (new ↔ review ↔ verified), so any active feed query has to
// refetch when EITHER event arrives. Pre-Codex-review only the saved
// event invalidated the feed, which meant another user's completion
// left stale Review/Verified lists on viewers until they refreshed.
function invalidateFeedOnEvent(es: EventSource, eventType: string, qc: QueryClient) {
  es.addEventListener(eventType, (e) => {
    const raw = (e as MessageEvent<string>).data
    try {
      JSON.parse(raw)
    } catch {
      return
    }
    void qc.invalidateQueries({ queryKey: ['feed'] })
  })
}

export function registerFeedHandlers(es: EventSource, opts: FeedHandlerOpts) {
  invalidateFeedOnEvent(es, 'annotation_saved', opts.qc)
  invalidateFeedOnEvent(es, 'annotation_completed', opts.qc)
}
