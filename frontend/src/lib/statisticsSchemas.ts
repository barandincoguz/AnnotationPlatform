import { z } from 'zod'

export const STATISTICS_PERIODS = ['today', 'last_7_days', 'last_30_days', 'all_time'] as const

export const statisticsPeriodSchema = z.enum(STATISTICS_PERIODS)

export const statisticsMetricsSchema = z.object({
  distinct_documents: z.number().int(),
  save_events: z.number().int(),
  complete_events: z.number().int(),
  uncomplete_events: z.number().int(),
  skip_events: z.number().int(),
  version_events: z.number().int(),
  create_versions: z.number().int(),
  edit_versions: z.number().int(),
  complete_mark_versions: z.number().int(),
  zero_diff_versions: z.number().int(),
  final_completed_documents: z.number().int(),
  xp_delta: z.number().int(),
})

export const statisticsPeriodMetricsSchema = z.object({
  today: statisticsMetricsSchema,
  last_7_days: statisticsMetricsSchema,
  last_30_days: statisticsMetricsSchema,
  all_time: statisticsMetricsSchema,
})

export const statisticsUserSchema = z.object({
  id: z.number().int(),
  username: z.string(),
  role: z.string(),
  avatar_color: z.string().nullable(),
})

export const statisticsUserRowSchema = z.object({
  user: statisticsUserSchema,
  xp_total: z.number().int(),
  badges_count: z.number().int(),
  streak_current: z.number().int(),
  last_active_date: z.string().nullable(),
  metrics: statisticsPeriodMetricsSchema,
})

export const statisticsResponseSchema = z.object({
  generated_at: z.string(),
  summary: statisticsPeriodMetricsSchema,
  users: z.array(statisticsUserRowSchema),
})

export type StatisticsPeriod = z.infer<typeof statisticsPeriodSchema>
export type StatisticsMetrics = z.infer<typeof statisticsMetricsSchema>
export type StatisticsPeriodMetrics = z.infer<typeof statisticsPeriodMetricsSchema>
export type StatisticsUserRow = z.infer<typeof statisticsUserRowSchema>
export type StatisticsResponse = z.infer<typeof statisticsResponseSchema>
