import { Button } from '@/components/ui/button'
import {
  useNotificationsHistory, useMarkReadMutation, useMarkAllReadMutation,
} from '@/api/queries/notifications'
import { NotificationItem } from './NotificationItem'
import { EmptyState } from '@/components/shell/EmptyState'

export function NotificationsList() {
  const history = useNotificationsHistory()
  const markRead = useMarkReadMutation()
  const markAllRead = useMarkAllReadMutation()

  if (history.isError) {
    return (
      <section id="notifications">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold">Bildirimler</h2>
        </div>
        <p className="text-sm text-warning">
          Bildirimler yüklenirken hata oluştu.{' '}
          <button
            type="button"
            className="underline"
            onClick={() => { void history.refetch() }}
          >
            Yeniden dene
          </button>
        </p>
      </section>
    )
  }

  if (history.isPending) {
    return (
      <section id="notifications">
        <h2 className="text-lg font-semibold mb-3">Bildirimler</h2>
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-12 animate-pulse rounded bg-muted" />
          ))}
        </div>
      </section>
    )
  }

  const items = history.data?.items ?? []
  const hasUnread = items.some((i) => !i.is_read)

  return (
    <section id="notifications">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Bildirimler</h2>
        {hasUnread && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => markAllRead.mutate()}
            disabled={markAllRead.isPending}
          >
            Tümünü okundu yap
          </Button>
        )}
      </div>
      {items.length === 0 ? (
        <EmptyState kicker="Boş" title="Henüz bildirim yok" />
      ) : (
        <ul>
          {items.map((item) => (
            <li key={item.id}>
              <NotificationItem item={item} onMarkRead={(id) => markRead.mutate(id)} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
