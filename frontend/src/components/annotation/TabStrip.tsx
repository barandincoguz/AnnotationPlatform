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
    activeRing:
      'data-[state=active]:ring-1 data-[state=active]:ring-accent2/40 data-[state=active]:text-accent2',
    iconClass: 'text-accent2',
  },
  {
    value: 'review',
    label: 'Kontrol Gerekiyor',
    Icon: Hourglass,
    activeRing:
      'data-[state=active]:ring-1 data-[state=active]:ring-accent/40 data-[state=active]:text-accent',
    iconClass: 'text-accent',
  },
  {
    value: 'verified',
    label: 'Tamamlanan',
    Icon: BadgeCheck,
    activeRing:
      'data-[state=active]:ring-1 data-[state=active]:ring-success/40 data-[state=active]:text-success',
    iconClass: 'text-success',
  },
]

export function TabStrip({ tab, onChange }: TabStripProps) {
  return (
    <Tabs value={tab} onValueChange={(v) => onChange(v as FeedTab)} className="w-full">
      <TabsList className="grid h-auto min-h-11 w-full grid-cols-3 items-stretch gap-1 bg-muted/70 p-1">
        {TABS.map(({ value, label, Icon, activeRing, iconClass }) => (
          <TabsTrigger
            key={value}
            value={value}
            className={`min-w-0 flex-col gap-0.5 whitespace-normal px-1 py-1.5 text-center text-[10px] font-bold leading-tight transition-all xl:flex-row xl:gap-1 xl:text-[11px] ${activeRing}`}
          >
            <Icon aria-hidden="true" className={`h-3.5 w-3.5 shrink-0 ${iconClass}`} />
            <span className="min-w-0 max-w-full break-words xl:flex-1">{label}</span>
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  )
}
