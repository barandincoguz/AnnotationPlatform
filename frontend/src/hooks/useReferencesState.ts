import { useEffect, useReducer, useRef } from 'react'
import type { components } from '@/api/types'

type ReferenceItem = components['schemas']['ReferenceItem']

type Action =
  | { type: 'init'; refs: ReferenceItem[] }
  | { type: 'add' }
  | { type: 'update'; index: number; ref: ReferenceItem }
  | { type: 'remove'; index: number }

const empty = (): ReferenceItem => ({
  kanun_no: null,
  kanun_ad: null,
  madde: null,
  fikra: null,
  bent: null,
  source_text: '',
})

function reducer(state: ReferenceItem[], action: Action): ReferenceItem[] {
  switch (action.type) {
    case 'init':
      return action.refs
    case 'add':
      return [...state, empty()]
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
  draftQueryStatus: 'pending' | 'success' | 'error'
  draftData: { references: ReferenceItem[] } | null
  annotationData: { references: ReferenceItem[] } | null
  onChange: (refs: ReferenceItem[]) => void
}

export function useReferencesState(opts: UseReferencesStateOpts) {
  const [list, dispatch] = useReducer(reducer, [])
  const hydratedRef = useRef(false)
  const onChangeRef = useRef(opts.onChange)
  onChangeRef.current = opts.onChange

  useEffect(() => {
    if (hydratedRef.current) return
    if (opts.draftQueryStatus !== 'success') return
    const initial = opts.draftData?.references ?? opts.annotationData?.references ?? []
    dispatch({ type: 'init', refs: initial })
    hydratedRef.current = true
  }, [opts.draftQueryStatus, opts.draftData, opts.annotationData])

  useEffect(() => {
    if (!hydratedRef.current) return
    onChangeRef.current(list)
  }, [list])

  return {
    list,
    add: () => dispatch({ type: 'add' }),
    update: (index: number, ref: ReferenceItem) => dispatch({ type: 'update', index, ref }),
    remove: (index: number) => dispatch({ type: 'remove', index }),
    hydrated: hydratedRef.current,
  }
}
