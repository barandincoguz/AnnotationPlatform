import { useRef, useEffect } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useFeed, type FeedTab } from '@/hooks/useFeed'
import { DocListItem } from './DocListItem'
import { EmptyState } from '@/components/shell/EmptyState'

// 4c: rows grew by ~16px after padding/text bumps; updated estimate so
// the virtualizer's first render allocates close to the true height
// (the measureElement ref re-corrects per-row regardless).
const ROW_HEIGHT_ESTIMATE = 128

// jsdom has no layout engine, so @tanstack/react-virtual reports an
// empty getVirtualItems() and rows never mount. The plan explicitly
// authorizes a test-mode bypass to a non-virtual list so the
// component's observable behaviour (rendered items, click→onSelectDoc,
// empty/loading states) can be asserted. In the browser the
// virtualizer runs normally.
const IS_TEST = import.meta.env.MODE === 'test'

interface DocListProps {
  tab: FeedTab
  selectedId: string | null
  onSelectDoc: (docId: string) => void
}

export function DocList({ tab, selectedId, onSelectDoc }: DocListProps) {
  const feed = useFeed(tab)
  const items = feed.data?.pages.flatMap((p) => p.items) ?? []
  const parentRef = useRef<HTMLDivElement>(null)

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT_ESTIMATE,
    overscan: 4,
  })

  useEffect(() => {
    if (IS_TEST) return
    const virtualItems = virtualizer.getVirtualItems()
    const last = virtualItems[virtualItems.length - 1]
    if (!last) return
    if (last.index >= items.length - 10 && feed.hasNextPage && !feed.isFetchingNextPage) {
      void feed.fetchNextPage()
    }
  }, [virtualizer, items.length, feed])

  if (feed.isPending) {
    return <div className="p-4 text-sm text-muted-foreground">Yükleniyor…</div>
  }
  if (items.length === 0) {
    return (
      <EmptyState
        kicker="Boş"
        title="Bu sekmede doküman yok"
        description="Bu sekmeye atanmış doküman bulunmuyor."
      />
    )
  }

  if (IS_TEST) {
    return (
      <div ref={parentRef} className="h-full overflow-auto">
        {items.map((item) => (
          <DocListItem
            key={item.document_id}
            item={item}
            isSelected={selectedId === item.document_id}
            onClick={() => onSelectDoc(item.document_id)}
          />
        ))}
      </div>
    )
  }

  return (
    <div ref={parentRef} className="h-full overflow-auto">
      <div
        style={{
          height: `${virtualizer.getTotalSize()}px`,
          width: '100%',
          position: 'relative',
        }}
      >
        {virtualizer.getVirtualItems().map((virtualRow) => {
          const item = items[virtualRow.index]!
          return (
            <div
              key={item.document_id}
              data-index={virtualRow.index}
              ref={virtualizer.measureElement}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualRow.start}px)`,
              }}
            >
              <DocListItem
                item={item}
                isSelected={selectedId === item.document_id}
                onClick={() => onSelectDoc(item.document_id)}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}
