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
  // Hydration must consult BOTH query statuses to avoid a race where the
  // draft endpoint resolves first (small response, or 404 for completed
  // docs whose draft was cleaned up), reports `draftData=null`, and the
  // hook commits an empty list while the annotation GET is still in
  // flight — locking hydratedRef=true so the late-arriving annotation
  // refs never make it to the UI. Symptom: refresh during page load
  // shows an empty reference panel until a subsequent refresh wins the
  // race with a different network timing.
  annotationQueryStatus: 'pending' | 'success' | 'error'
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
    if (hasDraftRefs) {
      // Draft wins; annotation status is irrelevant — even if annotation
      // hasn't resolved yet, the draft's content takes precedence
      // (drafts/{id} is per-user; annotation is shared; the per-user
      // draft is the canonical "what the user was last working on").
      lastOriginRef.current = 'init'
      dispatch({ type: 'init', refs: draftRefs })
      hydratedRef.current = true
      return
    }
    // Draft is empty or null — MUST wait for the annotation query to
    // settle before committing. Otherwise we'd lock hydratedRef=true
    // with an empty list while the real refs are still in flight (the
    // refresh-thrash bug: refs disappear until the next race lottery).
    if (opts.annotationQueryStatus !== 'success') return
    const annotationRefs = opts.annotationData?.references ?? []
    lastOriginRef.current = 'init'
    dispatch({ type: 'init', refs: annotationRefs })
    hydratedRef.current = true
  }, [
    sourceKey,
    opts.draftQueryStatus,
    opts.annotationQueryStatus,
    opts.draftData,
    opts.annotationData,
  ])

  useEffect(() => {
    if (!hydratedRef.current) return
    if (lastOriginRef.current !== 'user') return
    onChangeRef.current(list)
  }, [list])

  const userDispatch = (action: Action) => {
    if (!hydratedRef.current) return
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
