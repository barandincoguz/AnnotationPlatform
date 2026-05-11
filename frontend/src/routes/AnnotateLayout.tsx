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
    <div className="flex h-[calc(100vh-3rem)] flex-col">
      <div className="border-b border-border px-3 py-2">
        <TabStrip tab={tab} onChange={setTab} />
      </div>
      <div className="grid h-full grid-cols-[30%_1fr] overflow-hidden">
        <div className="border-r border-border overflow-hidden">
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
