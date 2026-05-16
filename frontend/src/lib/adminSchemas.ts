import { z } from 'zod'

// ---- audit ----
export const auditLogRowSchema = z.object({
  id: z.number().int(),
  admin_user_id: z.number().int().nullable(),
  admin_username: z.string().nullable(),
  action_type: z.string(),
  target_kind: z.string().nullable(),
  target_id: z.string().nullable(),
  metadata: z.string().nullable(),
  trace_id: z.string().nullable(),
  created_at: z.string(),
})
export const auditLogResponseSchema = z.object({
  items: z.array(auditLogRowSchema),
  total: z.number().int(),
  has_more: z.boolean(),
})
export type AuditLogRow = z.infer<typeof auditLogRowSchema>
export type AuditLogResponse = z.infer<typeof auditLogResponseSchema>

// ---- system events ----
export const systemEventRowSchema = z.object({
  id: z.number().int(),
  event_type: z.string(),
  severity: z.string(),
  message: z.string().nullable(),
  extra: z.string().nullable(),
  trace_id: z.string().nullable(),
  created_at: z.string(),
})
export const systemEventResponseSchema = z.object({
  items: z.array(systemEventRowSchema),
  total: z.number().int(),
  has_more: z.boolean(),
})
export type SystemEventRow = z.infer<typeof systemEventRowSchema>
export type SystemEventResponse = z.infer<typeof systemEventResponseSchema>

// ---- settings ----
export const settingValueSchema = z.union([z.number(), z.boolean(), z.string()])
export const settingsMapSchema = z.record(z.string(), settingValueSchema)
export type SettingValue = z.infer<typeof settingValueSchema>
export type SettingsMap = z.infer<typeof settingsMapSchema>

// ---- users ----
export const adminUserSchema = z.object({
  id: z.number().int(),
  username: z.string(),
  email: z.string().nullable(),
  role: z.enum(['admin', 'user']),
  is_active: z.boolean(),
  has_seen_manual: z.boolean(),
  has_passed_training: z.boolean(),
  avatar_color: z.string().nullable(),
  created_at: z.string(),
})
export const adminUsersListSchema = z.object({
  users: z.array(adminUserSchema),
  total: z.number().int(),
})
export type AdminUser = z.infer<typeof adminUserSchema>

// ---- gold docs ----
export const conceptSchema = z.object({
  kanun_no: z.string(),
  kanun_ad: z.string().nullish(),
  madde: z.string().nullish(),
  fikra: z.string().nullish(),
  bent: z.string().nullish(),
})
export type Concept = z.infer<typeof conceptSchema>

export const goldDocResolvedSchema = z.object({
  gold_id: z.string(),
  content: z.string(),
  expected_concepts: z.array(conceptSchema),
  min_concept_count: z.number().int(),
})

// Parses TEXT-stored JSON columns. Intentionally lets malformed JSON throw —
// admin panels are diagnostic surfaces, so a corrupted DB blob must surface
// as a parse error, not silently masquerade as empty data.
const parseJSONIfString = (v: unknown): unknown => {
  if (typeof v !== 'string') return v
  return JSON.parse(v)
}

export const goldDocOverrideSchema = z.object({
  gold_id: z.string(),
  is_deleted: z.number().int(),
  content: z.string().nullable(),
  expected_concepts: z.preprocess(parseJSONIfString, z.array(conceptSchema)).nullable().default([]),
  min_concept_count: z.number().int().nullable(),
  source: z.enum(['override', 'custom']),
  created_by_admin_id: z.number().int().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
})
export type GoldDocResolved = z.infer<typeof goldDocResolvedSchema>

export const goldDocsListResponseSchema = z.object({
  resolved: z.array(goldDocResolvedSchema),
  overrides: z.array(goldDocOverrideSchema),
})

// ---- quiz ----
export const quizQuestionResolvedSchema = z.object({
  id: z.string(),
  text: z.string(),
  choices: z.array(z.string()).length(4),
  correct_choice_idx: z.number().int().min(0).max(3),
})
export const quizOverrideSchema = z.object({
  question_id: z.string(),
  is_deleted: z.number().int(),
  text: z.string().nullable(),
  choices_json: z.string().nullable(),
  correct_choice_idx: z.number().int().nullable(),
  source: z.enum(['override', 'custom']),
  created_by_admin_id: z.number().int().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
})
export const quizListResponseSchema = z.object({
  resolved: z.array(quizQuestionResolvedSchema),
  overrides: z.array(quizOverrideSchema),
})
export type QuizQuestion = z.infer<typeof quizQuestionResolvedSchema>
