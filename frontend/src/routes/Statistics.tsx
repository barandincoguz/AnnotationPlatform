import { useMemo, useState } from 'react'
import { Award, CheckCircle2, FileText, Save, Search, Zap } from 'lucide-react'
import { useUserStatistics } from '@/api/queries/statistics'
import { AdminTable } from '@/components/admin/AdminTable'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type {
  StatisticsMetrics,
  StatisticsPeriod,
  StatisticsUserRow,
} from '@/lib/statisticsSchemas'

const FORMATTER = new Intl.NumberFormat('tr-TR')

const PERIOD_LABELS: Record<StatisticsPeriod, string> = {
  all_time: 'Toplam',
  today: 'Bugün',
  last_7_days: 'Son 7 gün',
  last_30_days: 'Son 30 gün',
}

const PERIOD_OPTIONS: StatisticsPeriod[] = ['all_time', 'today', 'last_7_days', 'last_30_days']

function formatNumber(value: number): string {
  return FORMATTER.format(value)
}

function SummaryCard({
  label,
  value,
  Icon,
  tone,
  ariaLabel,
}: {
  label: string
  value: number
  Icon: typeof FileText
  tone: string
  ariaLabel: string
}) {
  return (
    <Card className="border-border/70 bg-card/70">
      <CardContent className="flex items-center justify-between gap-4 p-4">
        <div className="min-w-0">
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            {label}
          </p>
          <p
            aria-label={ariaLabel}
            className="mt-1 font-display text-3xl font-semibold tabular-nums text-foreground"
          >
            {formatNumber(value)}
          </p>
        </div>
        <span
          aria-hidden
          className={`inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-md ${tone}`}
        >
          <Icon className="h-5 w-5" />
        </span>
      </CardContent>
    </Card>
  )
}

function getPeriodMetrics(row: StatisticsUserRow, period: StatisticsPeriod): StatisticsMetrics {
  return row.metrics[period]
}

export function Statistics() {
  const q = useUserStatistics()
  const [period, setPeriod] = useState<StatisticsPeriod>('all_time')
  const [search, setSearch] = useState('')

  const filteredUsers = useMemo(() => {
    const rows = q.data?.users ?? []
    const term = search.trim().toLocaleLowerCase('tr-TR')
    if (!term) return rows
    return rows.filter((row) => row.user.username.toLocaleLowerCase('tr-TR').includes(term))
  }, [q.data?.users, search])

  if (q.isError) {
    return (
      <div className="mx-auto max-w-6xl p-6">
        <div className="rounded-md border border-destructive/40 bg-card/70 p-4 text-sm text-foreground">
          İstatistikler yüklenemedi.{' '}
          <Button variant="link" className="h-auto p-0" onClick={() => void q.refetch()}>
            Yeniden dene
          </Button>
        </div>
      </div>
    )
  }

  const summary = q.data?.summary[period]

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
            Ekip · İstatistik
          </p>
          <h1 className="font-display text-3xl font-medium tracking-tight">
            Kullanıcı İstatistikleri
          </h1>
        </div>
        <Tabs value={period} onValueChange={(value) => setPeriod(value as StatisticsPeriod)}>
          <TabsList className="h-auto flex-wrap justify-start">
            {PERIOD_OPTIONS.map((option) => (
              <TabsTrigger key={option} value={option}>
                {PERIOD_LABELS[option]}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      {q.isPending || !summary ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-md bg-muted/70" />
          ))}
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <SummaryCard
            label="Doküman"
            value={summary.distinct_documents}
            ariaLabel="Özet doküman sayısı"
            Icon={FileText}
            tone="bg-info/12 text-info"
          />
          <SummaryCard
            label="Kaydetme"
            value={summary.save_events}
            ariaLabel="Özet kaydedilen doküman sayısı"
            Icon={Save}
            tone="bg-accent/12 text-accent"
          />
          <SummaryCard
            label="Tamamlama"
            value={summary.complete_events}
            ariaLabel="Özet tamamlanan doküman sayısı"
            Icon={CheckCircle2}
            tone="bg-success/12 text-success"
          />
          <SummaryCard
            label="XP"
            value={summary.xp_delta}
            ariaLabel="Özet XP değişimi"
            Icon={Zap}
            tone="bg-warning/12 text-warning"
          />
        </div>
      )}

      <div className="flex flex-wrap items-end gap-2 rounded-md border border-border/70 bg-card/50 p-3">
        <div className="flex min-w-[220px] flex-1 flex-col sm:max-w-xs">
          <label htmlFor="statistics-user-search" className="mb-1 text-xs text-muted-foreground">
            Kullanıcı ara
          </label>
          <div className="relative">
            <Search
              aria-hidden
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              id="statistics-user-search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="pl-9"
            />
          </div>
        </div>
        <div className="flex items-center gap-2 rounded-md border border-border/60 bg-background px-3 py-2 text-sm text-muted-foreground">
          <Award aria-hidden className="h-4 w-4 text-success" />
          <span className="tabular-nums">
            {q.data ? formatNumber(filteredUsers.length) : '—'} kullanıcı
          </span>
        </div>
      </div>

      <AdminTable<StatisticsUserRow>
        rows={filteredUsers}
        loading={q.isPending}
        emptyMessage="Eşleşen kullanıcı yok"
        getRowKey={(row) => row.user.id}
        columns={[
          {
            key: 'user',
            header: 'Kullanıcı',
            render: (row) => (
              <div className="flex min-w-[140px] items-center gap-2">
                <span
                  aria-hidden
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: row.user.avatar_color ?? 'hsl(var(--muted-foreground))' }}
                />
                <span className="font-medium">{row.user.username}</span>
              </div>
            ),
          },
          { key: 'xp_total', header: 'Toplam XP', render: (row) => formatNumber(row.xp_total) },
          { key: 'badges', header: 'Rozet', render: (row) => formatNumber(row.badges_count) },
          { key: 'streak', header: 'Streak', render: (row) => formatNumber(row.streak_current) },
          {
            key: 'last_active',
            header: 'Son Aktivite',
            render: (row) => row.last_active_date ?? '—',
          },
          {
            key: 'documents',
            header: 'Doküman',
            render: (row) => formatNumber(getPeriodMetrics(row, period).distinct_documents),
          },
          {
            key: 'saves',
            header: 'Kaydetme',
            render: (row) => formatNumber(getPeriodMetrics(row, period).save_events),
          },
          {
            key: 'complete',
            header: 'Tamamlama',
            render: (row) => formatNumber(getPeriodMetrics(row, period).complete_events),
          },
          {
            key: 'versions',
            header: 'Versiyon',
            render: (row) => formatNumber(getPeriodMetrics(row, period).version_events),
          },
          {
            key: 'xp_delta',
            header: 'XP Δ',
            render: (row) => formatNumber(getPeriodMetrics(row, period).xp_delta),
          },
        ]}
      />
    </div>
  )
}
