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
    // minus 4rem. Moving filters and tabs into the sidebar removes the
    // full-width top header completely, giving the reading & annotation
    // pane maximum possible dikey height (full remaining viewport).
    <div className="flex h-[calc(100vh-4rem)] bg-background overflow-hidden">
      <div className="grid w-full grid-cols-[30%_1fr] overflow-hidden">
        <div className="border-r border-border/70 overflow-hidden bg-card/30 flex flex-col h-full">
          <div className="space-y-2 border-b border-border/70 bg-card/45 px-3 py-2.5 shrink-0">
            <DocSearch className="w-full" />
            <div className="flex items-center gap-1.5 justify-between">
              <TabStrip tab={tab} onChange={setTab} />
              <SortMenu
                tab={tab}
                sort={sort}
                onChange={(next) => setSort(tab, next)}
              />
            </div>
          </div>
          <div className="flex-1 overflow-hidden">
            <DocList
              tab={tab}
              selectedId={docId ?? null}
              onSelectDoc={(id) => navigate(`/docs/${id}`)}
            />
          </div>
        </div>
        <div className="overflow-hidden h-full">
          <Outlet />
        </div>
      </div>
    </div>
  )
}
