import { z } from 'zod'

export const userSectionSchema = z.object({
  id: z.number().int(),
  username: z.string(),
  role: z.string(),
  avatar_color: z.string(),
})

export const xpSectionSchema = z.object({ total: z.number().int() })

export const streakSectionSchema = z.object({
  current: z.number().int(),
  longest: z.number().int(),
  last_active_date: z.string().nullable(),
})

export const todaySectionSchema = z.object({
  save: z.number().int(),
  complete: z.number().int(),
  review: z.number().int(),
  skip: z.number().int(),
  daily_target: z.number().int(),
})

export const badgeOutSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  earned_at: z.string(),
})

export const profileResponseSchema = z.object({
  user: userSectionSchema,
  xp: xpSectionSchema,
  streak: streakSectionSchema,
  today: todaySectionSchema,
  badges: z.array(badgeOutSchema),
})

// Notification uses backend shape: is_read (bool) + data (dict|null).
// Spec §3.1 (read_at) was outdated; backend is source of truth.
export const notificationSchema = z.object({
  id: z.number().int(),
  kind: z.string(),
  title: z.string(),
  body: z.string().nullable(),
  data: z.record(z.unknown()).nullable(),
  is_read: z.boolean(),
  created_at: z.string(),
})

export const notificationsListSchema = z.object({
  items: z.array(notificationSchema),
})

export const markAllReadResponseSchema = z.object({
  marked_count: z.number().int(),
})

export const badgesCatalogItemSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  criterion: z.string().nullable().optional(),
})

export const badgesCatalogSchema = z.array(badgesCatalogItemSchema)

export const onlineUserSchema = z.object({
  id: z.number().int(),
  username: z.string(),
  avatar_color: z.string(),
})

export const onlineUsersSchema = z.array(onlineUserSchema)

export type ProfileResponse = z.infer<typeof profileResponseSchema>
export type UserSection = z.infer<typeof userSectionSchema>
export type Notification = z.infer<typeof notificationSchema>
export type NotificationsList = z.infer<typeof notificationsListSchema>
export type MarkAllReadResponse = z.infer<typeof markAllReadResponseSchema>
export type BadgeCatalogItem = z.infer<typeof badgesCatalogItemSchema>
export type BadgesCatalog = z.infer<typeof badgesCatalogSchema>
export type OnlineUser = z.infer<typeof onlineUserSchema>
export type OnlineUsers = z.infer<typeof onlineUsersSchema>
export type BadgeOut = z.infer<typeof badgeOutSchema>
