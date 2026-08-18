import { useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useLawAbbreviationsQuery, type LawAbbreviation } from '@/api/queries/help'

interface LawAbbreviationListProps {
  /** 'compact' is tuned for the inline annotation popover; 'full' for the Help page. */
  variant?: 'full' | 'compact'
}

function trLower(s: string) {
  return s.toLocaleLowerCase('tr')
}

function matches(row: LawAbbreviation, q: string): boolean {
  if (!q) return true
  const needle = trLower(q.trim())
  if (trLower(row.name).includes(needle)) return true
  if (row.number?.includes(needle)) return true
  return row.abbrevs.some((a) => trLower(a).includes(needle))
}

export function LawAbbreviationList({ variant = 'full' }: LawAbbreviationListProps) {
  const query = useLawAbbreviationsQuery()
  const [q, setQ] = useState('')
  const compact = variant === 'compact'

  const filtered = useMemo(
    () => (query.data?.laws ?? []).filter((row) => matches(row, q)),
    [query.data, q],
  )

  const rows = (
    <ul className="divide-y divide-border/60">
      {filtered.map((row) => (
        <li key={row.name} className="flex items-start gap-3 py-2.5">
          <span className="mt-0.5 inline-flex min-w-[3rem] justify-center rounded-md bg-accent/10 px-2 py-0.5 font-mono text-[12px] font-semibold tabular-nums text-accent">
            {row.number ?? '—'}
          </span>
          <div className="min-w-0 flex-1">
            <p className={`font-medium leading-snug text-foreground ${compact ? 'text-[13px]' : 'text-[15px]'}`}>
              {row.name}
            </p>
            <div className="mt-1 flex flex-wrap gap-1">
              {row.abbrevs.map((a) => (
                <Badge key={a} variant="secondary" className="font-mono text-[10px] tracking-wide">
                  {a}
                </Badge>
              ))}
            </div>
          </div>
        </li>
      ))}
      {filtered.length === 0 && (
        <li className="py-6 text-center text-[13px] text-muted-foreground">
          Eşleşen kısaltma yok.
        </li>
      )}
    </ul>
  )

  return (
    <div className={compact ? 'w-[20rem] max-w-[85vw]' : ''}>
      <div className="relative">
        <Search
          aria-hidden
          className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Kısaltma, kanun adı veya numara ara…"
          aria-label="Kısaltma ara"
          className="pl-8"
        />
      </div>

      {query.isLoading && (
        <p className="py-4 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
          Yükleniyor…
        </p>
      )}
      {query.isError && (
        <p className="py-4 text-[13px] text-destructive" role="alert">
          Kısaltmalar yüklenemedi.
        </p>
      )}

      {!query.isLoading && !query.isError && (
        compact ? (
          <ScrollArea className="mt-2 h-[19rem] pr-3">{rows}</ScrollArea>
        ) : (
          <div className="mt-2">{rows}</div>
        )
      )}
    </div>
  )
}
