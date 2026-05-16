import { CheckCircle2, CircleDashed, Circle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { AttributionLabel } from './AttributionLabel'
import type { components } from '@/api/types'

type FeedItem = components['schemas']['FeedItem']

interface DocListItemProps {
  item: FeedItem
  isSelected: boolean
  onClick: () => void
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

export function DocListItem({ item, isSelected, onClick }: DocListItemProps) {
  return (
    <button
      type="button"
      onClick={onClick}
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
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-[12px] font-semibold uppercase tracking-[0.14em] text-foreground/80">
            № {item.sayi ?? '—'}
          </span>
          {item.tarih && (
            <span className="font-mono text-[11px] text-muted-foreground/80 tabular-nums">
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
