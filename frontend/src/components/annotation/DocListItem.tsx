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
    return <CheckCircle2 aria-label="tamamlandı" className="h-5 w-5 text-green-600" />
  }
  if (item.has_annotation) {
    return <CircleDashed aria-label="devam ediyor" className="h-5 w-5 text-amber-600" />
  }
  return <Circle aria-label="yeni" className="h-5 w-5 text-muted-foreground" />
}

export function DocListItem({ item, isSelected, onClick }: DocListItemProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex w-full flex-col gap-1 border-b border-border px-3 py-2 text-left transition-colors hover:bg-accent/40',
        isSelected && 'bg-accent border-l-2 border-l-primary',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="text-sm font-medium">
          #{item.sayi ?? '—'}
          {item.tarih && (
            <span className="ml-2 text-xs font-normal text-muted-foreground">{item.tarih}</span>
          )}
        </div>
        <StatusIcon item={item} />
      </div>
      <div className="line-clamp-2 text-sm text-foreground">
        {item.konu ?? <span className="italic text-muted-foreground">konu yok</span>}
      </div>
      {item.vergi_turu && (
        <div>
          <span className="inline-block rounded bg-muted px-2 py-0.5 text-xs">
            {item.vergi_turu}
          </span>
        </div>
      )}
      {item.has_annotation && (
        <div className="text-xs">
          <AttributionLabel username={item.last_editor_username} date={item.updated_at} />
        </div>
      )}
    </button>
  )
}
