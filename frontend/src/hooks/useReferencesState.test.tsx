import { describe, it, expect, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useReferencesState } from './useReferencesState'
import { makeReferenceItem } from '@/test/msw-handlers'

describe('useReferencesState', () => {
  it('initial state is empty until draft query resolves', () => {
    const { result } = renderHook(() =>
      useReferencesState({
        draftQueryStatus: 'pending',
        draftData: null,
        annotationData: null,
        onChange: vi.fn(),
      }),
    )
    expect(result.current.list).toEqual([])
    expect(result.current.hydrated).toBe(false)
  })

  it('hydrates from draft when present', () => {
    const ref = makeReferenceItem()
    const { result } = renderHook(() =>
      useReferencesState({
        draftQueryStatus: 'success',
        draftData: { references: [ref] },
        annotationData: { references: [makeReferenceItem({ madde: 'other' })] },
        onChange: vi.fn(),
      }),
    )
    expect(result.current.hydrated).toBe(true)
    expect(result.current.list).toEqual([ref])
  })

  it('falls back to annotation when no draft', () => {
    const ref = makeReferenceItem({ madde: 'X' })
    const { result } = renderHook(() =>
      useReferencesState({
        draftQueryStatus: 'success',
        draftData: null,
        annotationData: { references: [ref] },
        onChange: vi.fn(),
      }),
    )
    expect(result.current.list).toEqual([ref])
  })

  it('starts empty when neither draft nor annotation', () => {
    const { result } = renderHook(() =>
      useReferencesState({
        draftQueryStatus: 'success',
        draftData: null,
        annotationData: null,
        onChange: vi.fn(),
      }),
    )
    expect(result.current.list).toEqual([])
    expect(result.current.hydrated).toBe(true)
  })

  it('add/update/remove dispatch and propagate via onChange', () => {
    const onChange = vi.fn()
    const { result } = renderHook(() =>
      useReferencesState({
        draftQueryStatus: 'success',
        draftData: null,
        annotationData: null,
        onChange,
      }),
    )
    act(() => result.current.add())
    expect(result.current.list).toHaveLength(1)
    expect(onChange).toHaveBeenCalled()

    act(() => result.current.update(0, makeReferenceItem({ madde: 'NEW' })))
    expect(result.current.list[0]?.madde).toBe('NEW')

    act(() => result.current.remove(0))
    expect(result.current.list).toEqual([])
  })

  it('does NOT re-hydrate when inputs change after first hydration (F12)', () => {
    const ref1 = makeReferenceItem({ madde: '1' })
    const ref2 = makeReferenceItem({ madde: '2' })

    const { result, rerender } = renderHook(
      (props: {
        s: 'success'
        d: { references: ReturnType<typeof makeReferenceItem>[] } | null
        a: { references: ReturnType<typeof makeReferenceItem>[] } | null
      }) =>
        useReferencesState({
          draftQueryStatus: props.s,
          draftData: props.d,
          annotationData: props.a,
          onChange: vi.fn(),
        }),
      {
        initialProps: { s: 'success' as const, d: { references: [ref1] }, a: null },
      },
    )
    expect(result.current.list).toEqual([ref1])

    rerender({ s: 'success', d: { references: [ref2] }, a: null })
    expect(result.current.list).toEqual([ref1])
  })
})
