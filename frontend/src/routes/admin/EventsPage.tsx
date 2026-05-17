import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { AdminTable } from '@/components/admin/AdminTable'
import { DateRangePicker, type DateRange } from '@/components/admin/DateRangePicker'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useSystemEvents, type SystemEventsParams } from '@/api/queries/admin'
import { SeverityBadge } from '@/components/admin/SeverityBadge'
import type { SystemEventRow } from '@/lib/adminSchemas'

const PAGE_LIMIT = 50

export function EventsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [traceInput, setTraceInput] = useState(searchParams.get('trace_id') ?? '')
  const [eventTypeInput, setEventTypeInput] = useState(searchParams.get('event_type') ?? '')
  const [severityInput, setSeverityInput] = useState(searchParams.get('severity') ?? '')
  const [dateRange, setDateRange] = useState<DateRange | null>(null)
  const [offset, setOffset] = useState(0)

  useEffect(() => {
    setTraceInput(searchParams.get('trace_id') ?? '')
    setEventTypeInput(searchParams.get('event_type') ?? '')
    setSeverityInput(searchParams.get('severity') ?? '')
  }, [searchParams])

  const params: SystemEventsParams = { limit: PAGE_LIMIT, offset }
  if (traceInput) params.trace_id = traceInput
  if (eventTypeInput) params.event_type = eventTypeInput
  if (severityInput) params.severity = severityInput
  if (dateRange?.date_from) params.date_from = dateRange.date_from
  if (dateRange?.date_to) params.date_to = dateRange.date_to
  const q = useSystemEvents(params)

  const onApplyFilters = () => {
    const next = new URLSearchParams()
    if (traceInput) next.set('trace_id', traceInput)
    if (eventTypeInput) next.set('event_type', eventTypeInput)
    if (severityInput) next.set('severity', severityInput)
    setSearchParams(next)
    setOffset(0)
  }

  const onClearFilters = () => {
    setTraceInput(''); setEventTypeInput(''); setSeverityInput(''); setDateRange(null); setOffset(0)
    setSearchParams(new URLSearchParams())
  }

  const copyTrace = async (t: string) => {
    // See AuditPage: same defensive wrap so clipboard rejections become
    // a visible error rather than a swallowed promise.
    try {
      await navigator.clipboard.writeText(t)
      toast.success('Trace ID kopyalandı')
    } catch {
      toast.error('Kopyalanamadı')
    }
  }

  return (
    <div className="space-y-4">
      <div className="mb-6 space-y-1">
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
          Operations · Events
        </p>
        <h1 className="font-display text-3xl font-medium tracking-tight">
          System Events
        </h1>
        <p className="text-sm text-muted-foreground max-w-prose">
          Structured event stream for training, scoring, and system lifecycle activity.
        </p>
      </div>
      <div className="flex flex-wrap items-end gap-2 rounded-lg border border-border/70 bg-card/40 p-4">
        <div className="flex flex-col">
          <span className="mb-1 text-xs text-muted-foreground">Tarih</span>
          <DateRangePicker value={dateRange} onChange={(v) => { setDateRange(v); setOffset(0) }} />
        </div>
        <div className="flex flex-col">
          <label htmlFor="event-type-input" className="mb-1 text-xs text-muted-foreground">Event type</label>
          <Input id="event-type-input" aria-label="event type"
            value={eventTypeInput} onChange={(e) => setEventTypeInput(e.target.value)} placeholder="örn. training_pass" />
        </div>
        <div className="flex flex-col">
          <span className="mb-1 text-xs text-muted-foreground">Severity</span>
          <Select value={severityInput === '' ? 'all' : severityInput} onValueChange={(v) => setSeverityInput(v === 'all' ? '' : v)}>
            <SelectTrigger aria-label="Severity"><SelectValue placeholder="Tümü" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tümü</SelectItem>
              <SelectItem value="info">Info</SelectItem>
              <SelectItem value="warn">Warn</SelectItem>
              <SelectItem value="error">Error</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col">
          <label htmlFor="trace-input" className="mb-1 text-xs text-muted-foreground">Trace ID</label>
          <Input id="trace-input" aria-label="Trace ID ara"
            value={traceInput} onChange={(e) => setTraceInput(e.target.value)} placeholder="trace-..." />
        </div>
        <Button onClick={onApplyFilters}>Filtreyi uygula</Button>
        <Button variant="ghost" onClick={onClearFilters}>Temizle</Button>
      </div>

      {q.isError && (
        <div className="rounded border border-destructive p-4 text-sm">
          System events alınamadı.{' '}
          <Button variant="link" onClick={() => void q.refetch()}>Tekrar dene</Button>
        </div>
      )}

      <AdminTable<SystemEventRow>
        rows={q.data?.items ?? []}
        loading={q.isLoading}
        getRowKey={(r) => r.id}
        emptyMessage="Bu filtrelerle eşleşen kayıt yok"
        columns={[
          { key: 'ts', header: 'Zaman', render: (r) => r.created_at },
          { key: 'event_type', header: 'Event type', render: (r) => r.event_type },
          {
            key: 'severity', header: 'Severity', render: (r) => <SeverityBadge severity={r.severity} />,
          },
          { key: 'message', header: 'Message', render: (r) => r.message ?? <span className="text-muted-foreground">—</span> },
          {
            key: 'trace', header: 'Trace',
            render: (r) => r.trace_id
              ? <button className="text-xs text-primary hover:underline" onClick={() => void copyTrace(r.trace_id!)}>{r.trace_id}</button>
              : <span className="text-muted-foreground">—</span>,
          },
        ]}
      />

      <div className="flex items-center justify-between text-sm">
        <Button variant="outline" onClick={() => setOffset(Math.max(0, offset - PAGE_LIMIT))} disabled={offset === 0}>
          Önceki
        </Button>
        <span>
          {q.data ? (q.data.total === 0 ? '0 / 0' : `${offset + 1} - ${offset + q.data.items.length} / ${q.data.total}`) : ''}
        </span>
        <Button variant="outline" onClick={() => setOffset(offset + PAGE_LIMIT)} disabled={!q.data?.has_more}>
          Sonraki
        </Button>
      </div>
    </div>
  )
}
