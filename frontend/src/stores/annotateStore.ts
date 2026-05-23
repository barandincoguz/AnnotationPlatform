import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
// FeedTab is owned by the data layer (api/queries/feed). Re-export here
// so existing callers that pull `FeedTab` from the store don't break,
// but the type itself has a single definition site.
export type { FeedTab } from '@/api/queries/feed'
import type { FeedTab } from '@/api/queries/feed'

/**
 * Sort keys mirrored from backend/shuffle/service.py SORT_COLUMNS.
 * "shuffle" is the legacy per-user-per-day deterministic shuffle path;
 * any other key triggers a SQL ORDER BY on the matching column.
 *
 * Phase 6: `document_id` added as the cross-team canonical sort key
 * (= evrakOid). This is now the DEFAULT for all three tabs.
 *
 * Removed: 'sayi'. The per-year sayi was dropped from the doc display
 * (paket-6, commit 586b811: "drop misleading per-year № sayi") because
 * sayi is not unique across years. The SortMenu UI never rendered an
 * entry for it; keeping it in the type allowed a stale persisted sort
 * to survive rehydration and produce a sort the UI couldn't represent.
 */
export type SortKey =
  | 'document_id'
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
  document_id: ['new', 'review', 'verified'],
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
 * Phase 6: per-tab default sort = document_id DESC across the board.
 * Cross-team coordination: both this team and the partner team
 * (Zeynep) work the same özelge corpus and must see the same fixed
 * order. document_id (= evrakOid) lexicographic DESC matches the
 * partner DB's `evrak_id` DESC and is fully deterministic across
 * users. See backend/shuffle/service.py:DEFAULT_SORT_FOR for the
 * matching backend contract.
 */
const DEFAULT_SORT: Record<FeedTab, SortState> = {
  new: { by: 'document_id', order: 'desc' },
  review: { by: 'document_id', order: 'desc' },
  verified: { by: 'document_id', order: 'desc' },
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
      // Phase 6 bumped storage name v3 → v4 so all users seed cleanly
      // on the new cross-team default (document_id DESC). A surviving
      // v3 entry would persist the old per-tab defaults (tarih /
      // updated_at) and silently break the cross-team ordering
      // contract — bumping the key discards it on first load.
      name: 'annotate.store.v4',
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
)
