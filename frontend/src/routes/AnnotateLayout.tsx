import { useNavigate, useParams, Outlet } from 'react-router-dom'
import { DocList } from '@/components/annotation/DocList'
import { TabStrip } from '@/components/annotation/TabStrip'
import { SortMenu } from '@/components/annotation/SortMenu'
import { DocSearch } from '@/components/annotation/DocSearch'
import { useSSE } from '@/hooks/useSSE'
import { useAnnotateStore } from '@/stores/annotateStore'

export function AnnotateLayout() {
  const { docId } = useParams()
  const navigate = useNavigate()
  const tab = useAnnotateStore((s) => s.currentTab)
  const setTab = useAnnotateStore((s) => s.setCurrentTab)
  const sort = useAnnotateStore((s) => s.sort[s.currentTab])
  const setSort = useAnnotateStore((s) => s.setSort)

  useSSE({ acquiringDocId: null })

  return (
    // TopBar is h-16 (64px) post-4b, so the editor pane is viewport
    // minus 4rem rather than the pre-4b 3.5rem. Without this the bottom
    // 8px of the editor gets clipped on small displays.
    <div className="flex h-[calc(100vh-4rem)] flex-col bg-background">
      <div className="space-y-2.5 border-b border-border/70 bg-card/40 px-4 py-3">
        <div className="flex items-center gap-2">
          <DocSearch className="flex-1" />
          <SortMenu
            tab={tab}
            sort={sort}
            onChange={(next) => setSort(tab, next)}
          />
        </div>
        <TabStrip tab={tab} onChange={setTab} />
      </div>
      <div className="grid h-full grid-cols-[30%_1fr] overflow-hidden">
        <div className="border-r border-border/70 overflow-hidden bg-card/30">
          <DocList
            tab={tab}
            selectedId={docId ?? null}
            onSelectDoc={(id) => navigate(`/docs/${id}`)}
          />
        </div>
        <div className="overflow-hidden">
          <Outlet />
        </div>
      </div>
    </div>
  )
}
