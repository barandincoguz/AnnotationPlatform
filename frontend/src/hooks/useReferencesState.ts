import { useEffect, useReducer, useRef } from 'react'
import type { components } from '@/api/types'
import { emptyReferenceItem } from '@/lib/validateReferences'

type ReferenceItem = components['schemas']['ReferenceItem']

type Action =
  | { type: 'init'; refs: ReferenceItem[] }
  | { type: 'add' }
  | { type: 'update'; index: number; ref: ReferenceItem }
  | { type: 'remove'; index: number }

function reducer(state: ReferenceItem[], action: Action): ReferenceItem[] {
  switch (action.type) {
    case 'init':
      return action.refs
    case 'add':
      return [...state, emptyReferenceItem()]
    case 'update': {
      const next = state.slice()
      next[action.index] = action.ref
      return next
    }
    case 'remove':
      return state.filter((_, i) => i !== action.index)
  }
}

export interface UseReferencesStateOpts {
  sourceKey?: string
  draftQueryStatus: 'pending' | 'success' | 'error'
  draftData: { references: ReferenceItem[] } | null
  annotationData: { references: ReferenceItem[] } | null
  onChange: (refs: ReferenceItem[]) => void
}

type DispatchOrigin = 'init' | 'user'

export function useReferencesState(opts: UseReferencesStateOpts) {
  const [list, dispatch] = useReducer(reducer, [])
  const hydratedRef = useRef(false)
  const sourceKeyRef = useRef<string | null>(null)
  // Distinguishes server-driven hydration from user-driven mutations.
  // Only user mutations should propagate via onChange — otherwise the
  // initial hydrated value gets echoed back into draft.debouncedSave,
  // creating empty/stale drafts that later shadow the shared annotation.
  const lastOriginRef = useRef<DispatchOrigin>('init')
  const onChangeRef = useRef(opts.onChange)
  onChangeRef.current = opts.onChange
  const sourceKey = opts.sourceKey ?? '__default__'

  useEffect(() => {
    if (sourceKeyRef.current === sourceKey) return
    sourceKeyRef.current = sourceKey
    hydratedRef.current = false
    lastOriginRef.current = 'init'
    dispatch({ type: 'init', refs: [] })
  }, [sourceKey])

  useEffect(() => {
    if (hydratedRef.current) return
    if (opts.draftQueryStatus !== 'success') return
    // Empty draft refs are indistinguishable from "no draft" for hydration
    // purposes: they would otherwise shadow the shared annotation via the
    // `??` operator (empty array is not nullish). Fall through to the
    // annotation when the draft contains no rows.
    const draftRefs = opts.draftData?.references
    const hasDraftRefs = Array.isArray(draftRefs) && draftRefs.length > 0
    const initial = hasDraftRefs
      ? draftRefs
      : (opts.annotationData?.references ?? [])
    lastOriginRef.current = 'init'
    dispatch({ type: 'init', refs: initial })
    hydratedRef.current = true
  }, [sourceKey, opts.draftQueryStatus, opts.draftData, opts.annotationData])

  useEffect(() => {
    if (!hydratedRef.current) return
    if (lastOriginRef.current !== 'user') return
    onChangeRef.current(list)
  }, [list])

  const userDispatch = (action: Action) => {
    lastOriginRef.current = 'user'
    dispatch(action)
  }

  return {
    list,
    add: () => userDispatch({ type: 'add' }),
    update: (index: number, ref: ReferenceItem) =>
      userDispatch({ type: 'update', index, ref }),
    remove: (index: number) => userDispatch({ type: 'remove', index }),
    hydrated: hydratedRef.current,
  }
}
