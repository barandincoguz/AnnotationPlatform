import {
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  CalendarDays,
  Clock,
  Tag,
  Type,
  Gauge,
  AlignLeft,
  Users,
  Shuffle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  type FeedTab,
  type SortKey,
  type SortState,
  isSortAvailable,
} from '@/stores/annotateStore'

interface SortOption {
  key: SortKey
  label: string
  Icon: typeof CalendarDays
}

/**
 * Display order mirrors a "most common → least common" mental rank for
 * an annotation queue: dates first, then identifiers, then categorical,
 * then numeric/derived metadata, with shuffle as the explicit opt-out.
 */
const SORT_OPTIONS: SortOption[] = [
  { key: 'tarih', label: 'Tarih', Icon: CalendarDays },
  { key: 'updated_at', label: 'Son güncelleme', Icon: Clock },
  { key: 'created_at', label: 'Eklenme tarihi', Icon: Clock },
  { key: 'vergi_turu', label: 'Vergi türü', Icon: Tag },
  { key: 'konu', label: 'Konu', Icon: Type },
  { key: 'difficulty', label: 'Zorluk', Icon: Gauge },
  { key: 'word_count', label: 'Kelime sayısı', Icon: AlignLeft },
  { key: 'editors_count', label: 'Editör sayısı', Icon: Users },
  { key: 'shuffle', label: 'Karıştır', Icon: Shuffle },
]

interface SortMenuProps {
  tab: FeedTab
  sort: SortState
  onChange: (next: SortState) => void
}

/**
 * Sort selector for the doc list — icon-only trigger that opens a
 * popover with every whitelisted key. Clicking the active key toggles
 * the direction; clicking another key switches and resets direction
 * to desc. Keys not valid on the current tab (e.g. updated_at on the
 * "new" tab) appear disabled so the gate is visible rather than just
 * a 400 from the backend.
 */
export function SortMenu({ tab, sort, onChange }: SortMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="icon"
          aria-label="Sıralama"
          className="relative"
        >
          <ArrowUpDown />
          {/* Tiny direction marker so the icon button hints at active
              state without spelling out the full label. */}
          {sort.by !== 'shuffle' && (
            <span
              aria-hidden
              className="absolute -bottom-0.5 -right-0.5 inline-flex h-3 w-3 items-center justify-center rounded-full bg-accent text-accent-foreground"
            >
              {sort.order === 'desc' ? (
                <ArrowDown className="!h-2 !w-2" />
              ) : (
                <ArrowUp className="!h-2 !w-2" />
              )}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          Sıralama
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {SORT_OPTIONS.map(({ key, label, Icon }) => {
          const isActive = sort.by === key
          const disabled = !isSortAvailable(tab, key)
          // Shuffle never carries a direction in the UI — even when active,
          // suppress the arrow because "shuffled ascending" is meaningless.
          const showDirection = isActive && key !== 'shuffle'
          return (
            <DropdownMenuItem
              key={key}
              disabled={disabled}
              data-active={isActive ? 'true' : undefined}
              className="cursor-pointer gap-2.5 data-[active=true]:bg-accent/10 data-[active=true]:text-accent data-[active=true]:font-semibold"
              onSelect={(e) => {
                e.preventDefault()
                if (key === 'shuffle') {
                  onChange({ by: 'shuffle', order: 'desc' })
                  return
                }
                if (isActive) {
                  onChange({ by: key, order: sort.order === 'desc' ? 'asc' : 'desc' })
                } else {
                  onChange({ by: key, order: 'desc' })
                }
              }}
            >
              <Icon className="h-4 w-4 shrink-0 opacity-75" />
              <span className="flex-1">{label}</span>
              {showDirection && (
                sort.order === 'desc' ? (
                  <ArrowDown className="h-3.5 w-3.5 text-accent" />
                ) : (
                  <ArrowUp className="h-3.5 w-3.5 text-accent" />
                )
              )}
            </DropdownMenuItem>
          )
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
