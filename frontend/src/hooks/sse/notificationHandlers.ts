import type { QueryClient } from '@tanstack/react-query'
import { toast as defaultToast } from 'sonner'
import {
  badgeUnlockedSchema, speedWarningSchema, charLimitWarningSchema,
  parseEventData,
} from '@/lib/sseSchemas'
import { profileKeys } from '@/api/queries/profile'
import { notificationsKeys } from '@/api/queries/notifications'

interface NotificationHandlerOpts {
  qc: QueryClient
  toast?: typeof defaultToast
}

export function registerNotificationHandlers(
  es: EventSource, opts: NotificationHandlerOpts,
) {
  const t = opts.toast ?? defaultToast

  es.addEventListener('badge_unlocked', (e) => {
    const data = parseEventData(e, badgeUnlockedSchema)
    if (!data) return
    // Codex BROKEN-B: celebration toast is INFORMATIONAL ONLY.
    // No action button — clicking it would unmount AnnotateDoc and lose draft.
    t.success(`🎉 Yeni rozet: ${data.name}`, {
      duration: 15_000,
      description: data.description,
    })
    void opts.qc.invalidateQueries({ queryKey: profileKeys.all })
    void opts.qc.invalidateQueries({ queryKey: notificationsKeys.all })
  })

  es.addEventListener('speed_warning', (e) => {
    const data = parseEventData(e, speedWarningSchema)
    if (!data) return
    t.warning('Bir nefes al', {
      duration: 8_000,
      description: `Son ${data.window_minutes} dakikada ${data.save_count} kayıt attın. Kalite hızdan önemli.`,
    })
  })

  es.addEventListener('char_limit_warning', (e) => {
    const data = parseEventData(e, charLimitWarningSchema)
    if (!data) return
    t.warning('Metin uzunluğu dikkat', {
      duration: 8_000,
      description: `${data.ref_index + 1}. referansın metin alıntısı ${data.detail}.`,
    })
  })

  // Generic 'notification' event piggy-backs from gamification/service.py
  // alongside badge_unlocked. Bell counter must refresh.
  es.addEventListener('notification', () => {
    void opts.qc.invalidateQueries({ queryKey: notificationsKeys.all })
  })
}
