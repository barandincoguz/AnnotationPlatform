import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export type FeedTab = 'new' | 'review' | 'verified'

/**
 * Sort keys mirrored from backend/shuffle/service.py SORT_COLUMNS.
 * "shuffle" is the legacy per-user-per-day deterministic shuffle path;
 * any other key triggers a SQL ORDER BY on the matching column.
 *
 * Removed: 'sayi'. The per-year sayi was dropped from the doc display
 * (paket-6, commit 586b811: "drop misleading per-year № sayi") because
 * sayi is not unique across years. The SortMenu UI never rendered an
 * entry for it; keeping it in the type allowed a stale persisted sort
 * to survive rehydration and produce a sort the UI couldn't represent.
 */
export type SortKey =
  | 'shuffle'
  | 'tarih'
  | 'created_at'
  | 'vergi_turu'
  | 'konu'
  | 'difficulty'
  | 'word_count'
  | 'updated_at'
  | 'editors_count'

export type SortOrder = 'asc' | 'desc'

export interface SortState {
  by: SortKey
  order: SortOrder
}

/**
 * Sort keys backed by the annotation row (a.*) are only valid on tabs
 * that join the annotations table. Mirrors the tab-specific gate in
 * shuffle/service.py SORT_COLUMNS.
 */
const SORT_AVAILABILITY: Record<SortKey, readonly FeedTab[]> = {
  shuffle: ['new', 'review', 'verified'],
  tarih: ['new', 'review', 'verified'],
  created_at: ['new', 'review', 'verified'],
  vergi_turu: ['new', 'review', 'verified'],
  konu: ['new', 'review', 'verified'],
  difficulty: ['new', 'review', 'verified'],
  word_count: ['new', 'review', 'verified'],
  updated_at: ['review', 'verified'],
  editors_count: ['review', 'verified'],
}

export function isSortAvailable(tab: FeedTab, key: SortKey): boolean {
  return SORT_AVAILABILITY[key].includes(tab)
}

/**
 * Per-tab default sort. Picked so each tab opens on its most useful
 * first row: new docs sorted by özelge date desc, in-progress and
 * verified docs sorted by last activity desc.
 */
const DEFAULT_SORT: Record<FeedTab, SortState> = {
  new: { by: 'tarih', order: 'desc' },
  review: { by: 'updated_at', order: 'desc' },
  verified: { by: 'updated_at', order: 'desc' },
}

interface AnnotateState {
  currentTab: FeedTab
  sort: Record<FeedTab, SortState>
  setCurrentTab: (tab: FeedTab) => void
  setSort: (tab: FeedTab, sort: SortState) => void
}

export const useAnnotateStore = create<AnnotateState>()(
  persist(
    (set) => ({
      currentTab: 'new',
      sort: DEFAULT_SORT,
      setCurrentTab: (currentTab) => set({ currentTab }),
      setSort: (tab, next) =>
        set((state) => ({ sort: { ...state.sort, [tab]: next } })),
    }),
    {
      // Bumped storage name (v3) on removal of the 'sayi' SortKey: a
      // stale persisted `{by: 'sayi', order: 'desc'}` entry would
      // survive rehydration and trip the new sortKeySchema (`v3`
      // discards the old entry on parse failure rather than booting
      // into a sort the SortMenu can't display).
      name: 'annotate.store.v3',
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
)
