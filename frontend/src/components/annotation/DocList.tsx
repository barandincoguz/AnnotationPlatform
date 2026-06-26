import { useCallback, useRef, useEffect } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useFeed, type FeedTab } from '@/hooks/useFeed'
import { useAnnotateStore } from '@/stores/annotateStore'
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
  const sort = useAnnotateStore((s) => s.sort[tab])
  const feed = useFeed(tab, sort)
  const items = feed.data?.pages.flatMap((p) => p.items) ?? []
  const total = feed.data?.pages[0]?.total
  const countLabel = `${typeof total === 'number' ? total : items.length} kayıt`
  const parentRef = useRef<HTMLDivElement>(null)

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT_ESTIMATE,
    overscan: 4,
  })

  // Pull just the methods/flags this effect actually reads. Depending
  // on the whole `feed` object caused the effect to fire on every
  // render (TanStack returns a fresh wrapper each tick), defeating the
  // intent of the dependency array. `fetchNextPage` is referentially
  // stable on TanStack v5.
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = feed
  useEffect(() => {
    if (IS_TEST) return
    const virtualItems = virtualizer.getVirtualItems()
    const last = virtualItems[virtualItems.length - 1]
    if (!last) return
    if (last.index >= items.length - 10 && hasNextPage && !isFetchingNextPage) {
      void fetchNextPage()
    }
  }, [virtualizer, items.length, hasNextPage, isFetchingNextPage, fetchNextPage])

  // Stable handler so memoized DocListItem children don't bust their
  // memo on every parent re-render. Reading docId off the event target
  // keeps the closure dependency empty.
  const handleSelect = useCallback(
    (docId: string) => onSelectDoc(docId),
    [onSelectDoc],
  )

  if (feed.isPending) {
    return (
      <div role="status" aria-live="polite" className="p-4 text-sm text-muted-foreground">
        Yükleniyor…
      </div>
    )
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
      <div className="flex h-full min-h-0 flex-col">
        <div className="shrink-0 border-b border-border/60 px-5 py-2 font-mono text-[11px] font-semibold text-muted-foreground">
          {countLabel}
        </div>
        <div ref={parentRef} className="min-h-0 flex-1 overflow-auto">
          {items.map((item) => (
            <DocListItem
              key={item.document_id}
              item={item}
              isSelected={selectedId === item.document_id}
              onClick={handleSelect}
            />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-border/60 px-5 py-2 font-mono text-[11px] font-semibold text-muted-foreground">
        {countLabel}
      </div>
      <div ref={parentRef} className="min-h-0 flex-1 overflow-auto">
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
                  onClick={handleSelect}
                />
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
