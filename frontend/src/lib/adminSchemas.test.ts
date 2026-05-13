import { describe, it, expect } from 'vitest'
import {
  auditLogRowSchema, auditLogResponseSchema,
  settingValueSchema, settingsMapSchema,
  goldDocOverrideSchema,
} from './adminSchemas'

describe('auditLogRowSchema', () => {
  it('accepts valid row with admin_username string', () => {
    const ok = auditLogRowSchema.parse({
      id: 1, admin_user_id: 1, admin_username: 'root',
      action_type: 'promote', target_kind: 'user', target_id: '5',
      metadata: '{}', trace_id: 't-1', created_at: '2026-05-12T10:00:00+00:00',
    })
    expect(ok.admin_username).toBe('root')
  })

  it('accepts row with admin_username null (admin deleted)', () => {
    const ok = auditLogRowSchema.parse({
      id: 1, admin_user_id: 999, admin_username: null,
      action_type: 'x', target_kind: 'thing', target_id: '0',
      metadata: '{}', trace_id: null, created_at: '2026-05-12T10:00:00+00:00',
    })
    expect(ok.admin_username).toBeNull()
  })
})

describe('auditLogResponseSchema', () => {
  it('matches {items,total,has_more} backend shape', () => {
    const ok = auditLogResponseSchema.parse({
      items: [],
      total: 0,
      has_more: false,
    })
    expect(ok.has_more).toBe(false)
  })
})

describe('settingValueSchema', () => {
  it('accepts number / boolean / string', () => {
    expect(settingValueSchema.parse(5)).toBe(5)
    expect(settingValueSchema.parse(true)).toBe(true)
    expect(settingValueSchema.parse('hi')).toBe('hi')
  })
})

describe('settingsMapSchema', () => {
  it('accepts a key->primitive map', () => {
    const m = settingsMapSchema.parse({
      'training.quiz_pass_threshold': 4,
      'gamification.streak_enabled': true,
      'app.name': 'Annotation',
    })
    expect(m['training.quiz_pass_threshold']).toBe(4)
  })
})

describe('goldDocOverrideSchema', () => {
  it('parses expected_concepts from JSON string', () => {
    const ok = goldDocOverrideSchema.parse({
      gold_id: 'g_a',
      is_deleted: 0,
      content: 'doc',
      expected_concepts: '[{"kanun_no":"5520"}]',
      min_concept_count: 1,
      source: 'override',
      created_by_admin_id: 1,
      created_at: '2026-05-12',
      updated_at: '2026-05-12',
    })
    expect(ok.expected_concepts).toEqual([{ kanun_no: '5520' }])
  })

  it('passes through already-parsed expected_concepts array', () => {
    const ok = goldDocOverrideSchema.parse({
      gold_id: 'g_a',
      is_deleted: 0,
      content: 'doc',
      expected_concepts: [{ kanun_no: '5520' }],
      min_concept_count: 1,
      source: 'custom',
      created_by_admin_id: 1,
      created_at: '2026-05-12',
      updated_at: '2026-05-12',
    })
    expect(ok.expected_concepts).toEqual([{ kanun_no: '5520' }])
  })
})
