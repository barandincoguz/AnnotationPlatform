import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { client, unwrap } from '@/api/client'
import {
  auditLogResponseSchema, type AuditLogResponse,
  systemEventResponseSchema, type SystemEventResponse,
  settingsMapSchema, type SettingsMap, type SettingValue,
  adminUsersListSchema,
  goldDocsListResponseSchema,
  quizListResponseSchema,
} from '@/lib/adminSchemas'

// ---- Audit ----

export interface AuditQueryParams {
  limit?: number
  offset?: number
  admin_id?: number
  action?: string
  trace_id?: string
  date_from?: string
  date_to?: string
}

export function useAuditLog(p: AuditQueryParams) {
  return useQuery({
    queryKey: ['admin', 'audit-log', p],
    queryFn: async (): Promise<AuditLogResponse> => {
      const raw = await unwrap(
        await client.GET('/api/admin/audit-log', { params: { query: p } }),
      )
      return auditLogResponseSchema.parse(raw)
    },
  })
}

// ---- System events ----

export interface SystemEventsParams {
  limit?: number
  offset?: number
  event_type?: string
  severity?: string
  trace_id?: string
  date_from?: string
  date_to?: string
}

export function useSystemEvents(p: SystemEventsParams) {
  return useQuery({
    queryKey: ['admin', 'system-events', p],
    queryFn: async (): Promise<SystemEventResponse> => {
      const raw = await unwrap(
        await client.GET('/api/admin/system-events', { params: { query: p } }),
      )
      return systemEventResponseSchema.parse(raw)
    },
  })
}

// ---- Settings ----

export function useSettings() {
  return useQuery({
    queryKey: ['admin', 'settings'],
    queryFn: async (): Promise<SettingsMap> => {
      const raw = await unwrap(await client.GET('/api/admin/settings'))
      return settingsMapSchema.parse(raw)
    },
  })
}

export function useUpdateSettingMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (input: { key: string; value: SettingValue }) => {
      return unwrap(
        await client.PUT('/api/admin/settings/{key}', {
          params: { path: { key: input.key } },
          body: { value: input.value as never },
        }),
      )
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['admin', 'settings'] })
    },
  })
}

// ---- Users ----

export function useAdminUsers() {
  return useQuery({
    queryKey: ['admin', 'users'],
    queryFn: async () => {
      const raw = await unwrap(await client.GET('/api/admin/users'))
      return adminUsersListSchema.parse(raw)
    },
  })
}

// Inlined per-action mutations. openapi-fetch's typed paths reject
// dynamic strings (a factory passing a template-literal path as a
// variable widens to `string` which doesn't satisfy the PathsWithMethod
// union), so we keep four near-identical hooks instead.

export function usePromoteUserMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (user_id: number) =>
      unwrap(
        await client.POST('/api/admin/users/{user_id}/promote', {
          params: { path: { user_id } },
        }),
      ),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['admin', 'users'] })
    },
  })
}

export function useDemoteUserMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (user_id: number) =>
      unwrap(
        await client.POST('/api/admin/users/{user_id}/demote', {
          params: { path: { user_id } },
        }),
      ),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['admin', 'users'] })
    },
  })
}

export function useEnableUserMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (user_id: number) =>
      unwrap(
        await client.POST('/api/admin/users/{user_id}/enable', {
          params: { path: { user_id } },
        }),
      ),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['admin', 'users'] })
    },
  })
}

export function useDisableUserMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (user_id: number) =>
      unwrap(
        await client.POST('/api/admin/users/{user_id}/disable', {
          params: { path: { user_id } },
        }),
      ),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['admin', 'users'] })
    },
  })
}

export function useResetUserTrainingMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (user_id: number) =>
      unwrap(
        await client.POST('/api/admin/training/users/{user_id}/reset', {
          params: { path: { user_id } },
        }),
      ),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['admin', 'users'] })
    },
  })
}

export function useRotateInviteMutation() {
  return useMutation({
    mutationFn: async (new_code: string) => {
      const raw = await unwrap(
        await client.POST('/api/admin/invite/rotate', {
          body: { new_code },
        }),
      )
      return raw as { ok: boolean; new_code: string }
    },
  })
}

// ---- Locks ----

export function useForceReleaseLockMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (document_id: string) =>
      unwrap(
        await client.POST('/api/locks/{document_id}/admin/force-release', {
          params: { path: { document_id } },
        }),
      ),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['locks'] })
    },
  })
}

// ---- Gold docs ----

export function useAdminGoldDocs() {
  return useQuery({
    queryKey: ['admin', 'training', 'gold-docs'],
    queryFn: async () => {
      const raw = await unwrap(await client.GET('/api/admin/training/gold-docs'))
      return goldDocsListResponseSchema.parse(raw)
    },
  })
}

export function useUpsertGoldDocMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (input: {
      gold_id: string
      content: string
      expected_concepts: unknown[]
      min_concept_count: number
    }) =>
      unwrap(
        await client.PUT('/api/admin/training/gold-docs/{gold_id}', {
          params: { path: { gold_id: input.gold_id } },
          body: {
            content: input.content,
            expected_concepts: input.expected_concepts as never,
            min_concept_count: input.min_concept_count,
          },
        }),
      ),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['admin', 'training', 'gold-docs'] })
    },
  })
}

export function useDeleteGoldDocMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (gold_id: string) =>
      unwrap(
        await client.DELETE('/api/admin/training/gold-docs/{gold_id}', {
          params: { path: { gold_id } },
        }),
      ),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['admin', 'training', 'gold-docs'] })
    },
  })
}

// ---- Quiz ----

export function useAdminQuiz() {
  return useQuery({
    queryKey: ['admin', 'training', 'quiz'],
    queryFn: async () => {
      const raw = await unwrap(await client.GET('/api/admin/training/quiz'))
      return quizListResponseSchema.parse(raw)
    },
  })
}

export function useUpsertQuizMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (input: {
      question_id: string
      text: string
      choices: string[]
      correct_choice_idx: number
    }) =>
      unwrap(
        await client.PUT('/api/admin/training/quiz/{question_id}', {
          params: { path: { question_id: input.question_id } },
          body: {
            text: input.text,
            choices: input.choices,
            correct_choice_idx: input.correct_choice_idx,
          },
        }),
      ),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['admin', 'training', 'quiz'] })
    },
  })
}

export function useDeleteQuizMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (question_id: string) =>
      unwrap(
        await client.DELETE('/api/admin/training/quiz/{question_id}', {
          params: { path: { question_id } },
        }),
      ),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['admin', 'training', 'quiz'] })
    },
  })
}
