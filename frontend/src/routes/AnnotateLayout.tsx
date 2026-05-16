import { useNavigate, useParams, Outlet } from 'react-router-dom'
import { DocList } from '@/components/annotation/DocList'
import { TabStrip } from '@/components/annotation/TabStrip'
import { useSSE } from '@/hooks/useSSE'
import { useAnnotateStore } from '@/stores/annotateStore'

export function AnnotateLayout() {
  const { docId } = useParams()
  const navigate = useNavigate()
  const tab = useAnnotateStore((s) => s.currentTab)
  const setTab = useAnnotateStore((s) => s.setCurrentTab)

  useSSE({ acquiringDocId: null })

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col bg-background">
      <div className="border-b border-border/70 bg-card/40 px-4 py-2.5">
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
