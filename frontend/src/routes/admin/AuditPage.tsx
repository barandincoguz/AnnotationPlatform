import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { AdminTable } from '@/components/admin/AdminTable'
import { DateRangePicker, type DateRange } from '@/components/admin/DateRangePicker'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { useAuditLog, type AuditQueryParams } from '@/api/queries/admin'
import type { AuditLogRow } from '@/lib/adminSchemas'

const PAGE_LIMIT = 50

export function AuditPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [traceInput, setTraceInput] = useState(searchParams.get('trace_id') ?? '')
  const [actionInput, setActionInput] = useState(searchParams.get('action') ?? '')
  const [dateRange, setDateRange] = useState<DateRange | null>(null)
  const [offset, setOffset] = useState(0)

  useEffect(() => {
    setTraceInput(searchParams.get('trace_id') ?? '')
    setActionInput(searchParams.get('action') ?? '')
  }, [searchParams])

  const params: AuditQueryParams = { limit: PAGE_LIMIT, offset }
  if (traceInput) params.trace_id = traceInput
  if (actionInput) params.action = actionInput
  if (dateRange?.date_from) params.date_from = dateRange.date_from
  if (dateRange?.date_to) params.date_to = dateRange.date_to
  const q = useAuditLog(params)

  const onApplyFilters = () => {
    const next = new URLSearchParams()
    if (traceInput) next.set('trace_id', traceInput)
    if (actionInput) next.set('action', actionInput)
    setSearchParams(next)
    setOffset(0)
  }

  const onClearFilters = () => {
    setTraceInput(''); setActionInput(''); setDateRange(null); setOffset(0)
    setSearchParams(new URLSearchParams())
  }

  const copyTrace = async (t: string) => {
    // Wrap the write in try/catch so a clipboard rejection (insecure
    // context, permission denied) surfaces as an error toast instead
    // of an uncaught promise + dead button.
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
          Operations · Audit
        </p>
        <h1 className="font-display text-3xl font-medium tracking-tight">
          Audit Log
        </h1>
        <p className="text-sm text-muted-foreground max-w-prose">
          Immutable record of every admin action performed on the platform.
        </p>
      </div>
      <div className="flex flex-wrap items-end gap-2 rounded-lg border border-border/70 bg-card/40 p-4">
        <div className="flex flex-col">
          <span className="mb-1 text-xs text-muted-foreground">Tarih</span>
          <DateRangePicker value={dateRange} onChange={(v) => { setDateRange(v); setOffset(0) }} />
        </div>
        <div className="flex flex-col">
          <label htmlFor="audit-action" className="mb-1 text-xs text-muted-foreground">Action type</label>
          <Input id="audit-action" value={actionInput} onChange={(e) => setActionInput(e.target.value)} placeholder="örn. promote" />
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
          Audit log alınamadı.{' '}
          <Button variant="link" onClick={() => void q.refetch()}>Tekrar dene</Button>
        </div>
      )}

      <AdminTable<AuditLogRow>
        rows={q.data?.items ?? []}
        loading={q.isLoading}
        getRowKey={(r) => r.id}
        emptyMessage="Bu filtrelerle eşleşen kayıt yok"
        columns={[
          { key: 'ts', header: 'Zaman', render: (r) => r.created_at },
          { key: 'admin', header: 'Admin', render: (r) => r.admin_username ?? `#${r.admin_user_id ?? '?'}` },
          { key: 'action', header: 'Action', render: (r) => r.action_type },
          { key: 'target', header: 'Target', render: (r) => `${r.target_kind ?? ''}:${r.target_id ?? ''}` },
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
