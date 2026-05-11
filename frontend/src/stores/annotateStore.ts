import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export type FeedTab = 'new' | 'review' | 'verified'

interface AnnotateState {
  currentTab: FeedTab
  setCurrentTab: (tab: FeedTab) => void
}

export const useAnnotateStore = create<AnnotateState>()(
  persist(
    (set) => ({
      currentTab: 'new',
      setCurrentTab: (currentTab) => set({ currentTab }),
    }),
    {
      name: 'annotate.currentTab',
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
)
