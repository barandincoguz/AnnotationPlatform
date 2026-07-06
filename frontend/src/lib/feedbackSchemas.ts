import { z } from 'zod'

export const feedbackTypeSchema = z.enum(['complaint', 'suggestion'])
export type FeedbackType = z.infer<typeof feedbackTypeSchema>

export const feedbackCreateRequestSchema = z.object({
  type: feedbackTypeSchema,
  message: z.string(),
})
export type FeedbackCreateRequest = z.infer<typeof feedbackCreateRequestSchema>

export const feedbackRowSchema = z.object({
  id: z.number().int(),
  user_id: z.number().int(),
  username: z.string(),
  type: feedbackTypeSchema,
  message: z.string(),
  created_at: z.string(),
})
export type FeedbackRow = z.infer<typeof feedbackRowSchema>

export const feedbackListResponseSchema = z.array(feedbackRowSchema)

