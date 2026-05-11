import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { QueryClient } from '@tanstack/react-query'
import { registerNotificationHandlers } from './notificationHandlers'

function makeFakeES() {
  const listeners: Record<string, Array<(e: MessageEvent) => void>> = {}
  return {
    addEventListener(type: string, fn: (e: MessageEvent) => void) {
      listeners[type] = [...(listeners[type] ?? []), fn]
    },
    dispatch(type: string, dataObj: unknown) {
      const e = new MessageEvent(type, { data: JSON.stringify(dataObj) })
      for (const fn of listeners[type] ?? []) fn(e)
    },
  }
}

describe('registerNotificationHandlers', () => {
  let qc: { invalidateQueries: ReturnType<typeof vi.fn> }
  let toastSuccess: ReturnType<typeof vi.fn>
  let toastWarning: ReturnType<typeof vi.fn>

  beforeEach(() => {
    qc = { invalidateQueries: vi.fn() }
    toastSuccess = vi.fn()
    toastWarning = vi.fn()
  })

  it('badge_unlocked: 15s celebration toast (no action button) + invalidates profile + notifications', () => {
    const es = makeFakeES()
    registerNotificationHandlers(es as never, {
      qc: qc as unknown as QueryClient,
      toast: { success: toastSuccess, warning: toastWarning } as never,
    })
    es.dispatch('badge_unlocked', {
      badge_id: 'first_annotation',
      name: 'İlk Annotation',
      description: 'İlk kayıt başarıyla yapıldı.',
      earned_at: '2026-05-11T00:00:00+00:00',
    })
    expect(toastSuccess).toHaveBeenCalledWith(
      expect.stringContaining('İlk Annotation'),
      expect.objectContaining({ duration: 15_000 }),
    )
    const optsArg = toastSuccess.mock.calls[0][1] as Record<string, unknown>
    // Codex BROKEN-B: must NOT have an action property
    expect(optsArg).not.toHaveProperty('action')
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['profile'] })
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['notifications'] })
  })

  it('speed_warning: gentle warning toast 8s', () => {
    const es = makeFakeES()
    registerNotificationHandlers(es as never, {
      qc: qc as unknown as QueryClient,
      toast: { success: toastSuccess, warning: toastWarning } as never,
    })
    es.dispatch('speed_warning', { window_minutes: 5, save_count: 6 })
    expect(toastWarning).toHaveBeenCalledWith(
      'Bir nefes al',
      expect.objectContaining({ duration: 8_000 }),
    )
  })

  it('char_limit_warning: gentle warning toast 8s', () => {
    const es = makeFakeES()
    registerNotificationHandlers(es as never, {
      qc: qc as unknown as QueryClient,
      toast: { success: toastSuccess, warning: toastWarning } as never,
    })
    es.dispatch('char_limit_warning', { ref_index: 2, detail: 'çok uzun' })
    expect(toastWarning).toHaveBeenCalledWith(
      'Metin uzunluğu dikkat',
      expect.objectContaining({ duration: 8_000 }),
    )
  })

  it('generic notification SSE invalidates notifications cache', () => {
    const es = makeFakeES()
    registerNotificationHandlers(es as never, {
      qc: qc as unknown as QueryClient,
      toast: { success: toastSuccess, warning: toastWarning } as never,
    })
    es.dispatch('notification', { kind: 'badge_unlocked', data: {} })
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['notifications'] })
  })

  it('malformed payload silently dropped', () => {
    const es = makeFakeES()
    registerNotificationHandlers(es as never, {
      qc: qc as unknown as QueryClient,
      toast: { success: toastSuccess, warning: toastWarning } as never,
    })
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    es.dispatch('badge_unlocked', { broken: 'shape' })
    expect(toastSuccess).not.toHaveBeenCalled()
    warn.mockRestore()
  })
})
