import { Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { formatRelativeTr } from '@/lib/formatters'
import { iconForKind } from '@/lib/notificationKinds'
import type { Notification } from '@/lib/profileSchemas'

interface NotificationItemProps {
  item: Notification
  onMarkRead: (id: number) => void
}

export function NotificationItem({ item, onMarkRead }: NotificationItemProps) {
  const unread = !item.is_read
  return (
    <div
      className={cn(
        'flex items-start gap-3 border-b py-3 border-l-2',
        unread && 'bg-accent/5 border-l-accent pl-3 font-medium',
        !unread && 'border-l-transparent',
      )}
    >
      <span className="inline-flex items-center justify-center h-6 w-6 rounded-full bg-muted/40" aria-hidden="true">{iconForKind(item.kind)}</span>
      <div className="flex-1 min-w-0">
        <h4 className="truncate" title={item.title}>{item.title}</h4>
        {item.body && (
          <p className="text-sm text-muted-foreground line-clamp-2">{item.body}</p>
        )}
        <time className="text-xs text-muted-foreground">
          {formatRelativeTr(item.created_at)}
        </time>
      </div>
      {unread && (
        <Button
          variant="ghost"
          size="sm"
          aria-label={`${item.title} bildirimini okundu işaretle`}
          onClick={() => onMarkRead(item.id)}
        >
          <Check className="h-4 w-4" />
        </Button>
      )}
    </div>
  )
}
