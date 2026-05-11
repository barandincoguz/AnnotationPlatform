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
    // Codex BROKEN-E: SSE drops leave indefinite stale state without polling.
    refetchInterval: 30_000,
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
