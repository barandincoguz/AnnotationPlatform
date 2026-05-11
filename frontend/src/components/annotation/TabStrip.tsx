import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { FeedTab } from '@/hooks/useFeed'

interface TabStripProps {
  tab: FeedTab
  onChange: (tab: FeedTab) => void
}

export function TabStrip({ tab, onChange }: TabStripProps) {
  return (
    <Tabs value={tab} onValueChange={(v) => onChange(v as FeedTab)}>
      <TabsList>
        <TabsTrigger value="new">Yeni</TabsTrigger>
        <TabsTrigger value="review">Devam Eden</TabsTrigger>
        <TabsTrigger value="verified">Tamamlanan</TabsTrigger>
      </TabsList>
    </Tabs>
  )
}
