import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { client, unwrap, unwrapVoid } from '@/api/client'
import {
  notificationsListSchema, markAllReadResponseSchema,
  type NotificationsList, type MarkAllReadResponse,
} from '@/lib/profileSchemas'

export const notificationsKeys = {
  all: ['notifications'] as const,
  unread: () => [...notificationsKeys.all, 'unread'] as const,
  history: () => [...notificationsKeys.all, 'history'] as const,
}

export function useUnreadNotifications() {
  return useQuery<NotificationsList>({
    queryKey: notificationsKeys.unread(),
    queryFn: async () => {
      const raw = await unwrap(await client.GET('/api/me/notifications', {
        params: { query: { unread_only: true, limit: 50 } },
      }))
      return notificationsListSchema.parse(raw)
    },
    staleTime: 5_000,
    // SSE drops would leave indefinite stale state without polling, but the
    // 30s cadence + windowFocus refetch + same-key refetch on every
    // notification mutation produced a ~3 req/min idle baseline AND a
    // 3-fetch thunder on every tab-return (paired with useProfile +
    // useOnlineUsers). Doubled to 60s — humans don't notice the extra
    // 30s of staleness on a chat-style notification surface, and the
    // SSE channel still invalidates immediately on real events.
    refetchInterval: 60_000,
  })
}

export function useNotificationsHistory() {
  return useQuery<NotificationsList>({
    queryKey: notificationsKeys.history(),
    queryFn: async () => {
      const raw = await unwrap(await client.GET('/api/me/notifications', {
        params: { query: { unread_only: false, limit: 50 } },
      }))
      return notificationsListSchema.parse(raw)
    },
    staleTime: 5_000,
    refetchOnWindowFocus: true,
  })
}

export function useMarkReadMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) =>
      unwrapVoid(await client.POST('/api/me/notifications/{notification_id}/read', {
        params: { path: { notification_id: id } },
      })),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: notificationsKeys.all })
    },
  })
}

export function useMarkAllReadMutation() {
  const qc = useQueryClient()
  return useMutation<MarkAllReadResponse>({
    mutationFn: async () => {
      const raw = await unwrap(await client.POST('/api/me/notifications/read-all'))
      return markAllReadResponseSchema.parse(raw)
    },
    onSuccess: (data) => {
      void qc.invalidateQueries({ queryKey: notificationsKeys.all })
      toast.success(`${data.marked_count} bildirim okundu işaretlendi.`)
    },
  })
}
