import { Sparkles, Hourglass, BadgeCheck } from 'lucide-react'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { FeedTab } from '@/hooks/useFeed'

interface TabStripProps {
  tab: FeedTab
  onChange: (tab: FeedTab) => void
}

interface TabDef {
  value: FeedTab
  label: string
  Icon: typeof Sparkles
  /** Tailwind class applied only when the tab is active. */
  activeRing: string
  /** Icon tint per tab — semantic color identity. */
  iconClass: string
}

const TABS: TabDef[] = [
  {
    value: 'new',
    label: 'Yeni',
    Icon: Sparkles,
    activeRing: 'data-[state=active]:ring-1 data-[state=active]:ring-accent2/40 data-[state=active]:text-accent2',
    iconClass: 'text-accent2',
  },
  {
    value: 'review',
    label: 'Devam Eden',
    Icon: Hourglass,
    activeRing: 'data-[state=active]:ring-1 data-[state=active]:ring-accent/40 data-[state=active]:text-accent',
    iconClass: 'text-accent',
  },
  {
    value: 'verified',
    label: 'Tamamlanan',
    Icon: BadgeCheck,
    activeRing: 'data-[state=active]:ring-1 data-[state=active]:ring-success/40 data-[state=active]:text-success',
    iconClass: 'text-success',
  },
]

export function TabStrip({ tab, onChange }: TabStripProps) {
  return (
    <Tabs value={tab} onValueChange={(v) => onChange(v as FeedTab)}>
      <TabsList className="h-11 gap-1 bg-muted/70 p-1">
        {TABS.map(({ value, label, Icon, activeRing, iconClass }) => (
          <TabsTrigger
            key={value}
            value={value}
            className={`gap-2 px-4 py-2 text-[15px] font-semibold transition-all ${activeRing}`}
          >
            <Icon aria-hidden="true" className={`h-4 w-4 ${iconClass}`} />
            {label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  )
}
