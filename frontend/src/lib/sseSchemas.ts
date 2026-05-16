import { z } from 'zod'

// Backend gamification.service.run_after_save publishes badge_unlocked with
// {badge_id, name, description, earned_at} (see _publish_unlock_events).
export const badgeUnlockedSchema = z.object({
  badge_id: z.string(),
  name: z.string(),
  description: z.string(),
  earned_at: z.string(),
})

export const speedWarningSchema = z.object({
  window_minutes: z.number().int(),
  save_count: z.number().int(),
})

export const charLimitWarningSchema = z.object({
  ref_index: z.number().int(),
  detail: z.string(),
})

export const userOnlinePayloadSchema = z.object({
  id: z.number().int(),
  username: z.string(),
  avatar_color: z.string().nullable(),
})

export const userOfflinePayloadSchema = z.object({
  id: z.number().int(),
})

/** Parse e.data (JSON string) and validate against a Zod schema. Logs a
 * warning and returns null on any failure — never throws. SSE handlers
 * must keep running even on one malformed event. */
export function parseEventData<T>(
  e: MessageEvent,
  schema: z.ZodType<T>,
): T | null {
  let raw: unknown
  try {
    raw = JSON.parse(e.data as string)
  } catch {
    return null
  }
  const result = schema.safeParse(raw)
  if (!result.success) {
    console.warn('[SSE] payload parse failed', e.type, result.error.issues)
    return null
  }
  return result.data
}

export type BadgeUnlockedPayload = z.infer<typeof badgeUnlockedSchema>
export type SpeedWarningPayload = z.infer<typeof speedWarningSchema>
export type CharLimitWarningPayload = z.infer<typeof charLimitWarningSchema>
export type UserOnlinePayload = z.infer<typeof userOnlinePayloadSchema>
export type UserOfflinePayload = z.infer<typeof userOfflinePayloadSchema>
