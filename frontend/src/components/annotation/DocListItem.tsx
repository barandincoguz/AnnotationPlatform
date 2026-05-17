import { memo } from 'react'
import { CheckCircle2, CircleDashed, Circle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { AttributionLabel } from './AttributionLabel'
import type { components } from '@/api/types'

type FeedItem = components['schemas']['FeedItem']

interface DocListItemProps {
  item: FeedItem
  isSelected: boolean
  // Parent passes a stable `(docId: string) => void`; the row passes
  // its own document_id back, so the closure on the button stays
  // referentially stable across re-renders. This pairs with the
  // `React.memo` wrapper below to keep the virtualized window from
  // re-rendering every visible row on any parent state tick (SSE
  // invalidations are the hottest source).
  onClick: (docId: string) => void
}

function StatusIcon({ item }: { item: FeedItem }) {
  if (item.is_completed) {
    return (
      <CheckCircle2
        aria-label="tamamlandı"
        className="h-5 w-5 text-success shrink-0"
        strokeWidth={2.25}
      />
    )
  }
  if (item.has_annotation) {
    return (
      <CircleDashed
        aria-label="devam ediyor"
        className="h-5 w-5 text-accent shrink-0"
        strokeWidth={2.25}
      />
    )
  }
  return (
    <Circle
      aria-label="yeni"
      className="h-5 w-5 text-accent2 shrink-0"
      strokeWidth={2.25}
    />
  )
}

function DocListItemImpl({ item, isSelected, onClick }: DocListItemProps) {
  return (
    <button
      type="button"
      onClick={() => onClick(item.document_id)}
      className={cn(
        'group relative flex w-full flex-col gap-2 border-b border-border/60 px-5 py-4 text-left transition-colors',
        'hover:bg-muted/60 focus-visible:outline-none focus-visible:bg-muted/80',
        isSelected && 'bg-secondary/70',
      )}
    >
      {isSelected && (
        <span
          aria-hidden
          className="absolute inset-y-0 left-0 w-1 bg-accent"
        />
      )}
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col gap-0.5 min-w-0">
          <span
            title={item.document_id}
            className="font-mono text-[13px] font-bold tracking-[0.04em] text-foreground/90 truncate"
          >
            {item.document_id}
          </span>
          {item.tarih && (
            <span className="font-mono text-[10px] text-muted-foreground/80 tabular-nums">
              {item.tarih}
            </span>
          )}
        </div>
        <StatusIcon item={item} />
      </div>
      <div className="line-clamp-2 text-[15px] font-medium leading-snug text-foreground">
        {item.konu ?? <span className="italic text-muted-foreground">konu yok</span>}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {item.vergi_turu && (
          <span className="inline-flex items-center rounded-full border border-accent2/30 bg-accent2/10 px-2.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-accent2">
            {item.vergi_turu}
          </span>
        )}
        {item.has_annotation && (
          <AttributionLabel
            username={item.last_editor_username}
            date={item.updated_at}
          />
        )}
      </div>
    </button>
  )
}

// React.memo on the row keeps the virtualized window from re-rendering
// every visible row when the parent rerenders without changing per-row
// props (e.g. SSE invalidates the feed, the items array gets a new
// reference but the underlying rows are equal). With the stable
// onClick contract above, default props equality is sufficient — no
// custom areEqual needed.
export const DocListItem = memo(DocListItemImpl)
