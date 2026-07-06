import { useMemo, useState } from 'react'
import { MessageSquareText } from 'lucide-react'
import { AdminTable } from '@/components/admin/AdminTable'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useFeedbackList } from '@/api/queries/feedback'
import type { FeedbackRow, FeedbackType } from '@/lib/feedbackSchemas'

type FeedbackFilter = FeedbackType | 'all'

const MESSAGE_LIMIT = 140

function TypeBadge({ type }: { type: FeedbackType }) {
  if (type === 'complaint') {
    return <Badge className="border-warning/30 bg-warning/10 text-warning hover:bg-warning/10">Şikayet</Badge>
  }
  return <Badge className="border-success/30 bg-success/10 text-success hover:bg-success/10">Öneri</Badge>
}

function MessageCell({
  row,
  expanded,
  onToggle,
}: {
  row: FeedbackRow
  expanded: boolean
  onToggle: () => void
}) {
  const isLong = row.message.length > MESSAGE_LIMIT
  const visible = !isLong || expanded ? row.message : `${row.message.slice(0, MESSAGE_LIMIT)}...`
  return (
    <div className="max-w-[520px] space-y-1">
      <p className="whitespace-pre-wrap break-words leading-relaxed">{visible}</p>
      {isLong && (
        <Button type="button" variant="link" className="h-auto p-0 text-xs" onClick={onToggle}>
          {expanded ? 'Kısalt' : 'Devamını göster'}
        </Button>
      )}
    </div>
  )
}

export function FeedbackPage() {
  const [filter, setFilter] = useState<FeedbackFilter>('all')
  const [expandedIds, setExpandedIds] = useState<Set<number>>(() => new Set())
  const typeFilter = filter === 'all' ? undefined : filter
  const q = useFeedbackList(typeFilter)

  const counts = useMemo(() => {
    const rows = q.data ?? []
    return {
      total: rows.length,
      complaint: rows.filter((row) => row.type === 'complaint').length,
      suggestion: rows.filter((row) => row.type === 'suggestion').length,
    }
  }, [q.data])

  const toggleExpanded = (id: number) => {
    setExpandedIds((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
            People · Feedback
          </p>
          <h1 className="font-display text-3xl font-medium tracking-tight">
            Feedback
          </h1>
        </div>
        <div className="flex items-center gap-2 rounded-md border border-border/70 bg-card/40 px-3 py-2 text-sm text-muted-foreground">
          <MessageSquareText aria-hidden className="h-4 w-4 text-accent" />
          <span className="tabular-nums">
            {counts.total} total · {counts.complaint} complaint · {counts.suggestion} suggestion
          </span>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-2 rounded-md border border-border/70 bg-card/40 p-4">
        <div className="flex flex-col">
          <span className="mb-1 text-xs text-muted-foreground">Tip filtresi</span>
          <Select value={filter} onValueChange={(value) => setFilter(value as FeedbackFilter)}>
            <SelectTrigger aria-label="Tip filtresi" className="min-w-[180px] bg-card">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tümü</SelectItem>
              <SelectItem value="complaint">Şikayet</SelectItem>
              <SelectItem value="suggestion">Öneri</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {q.isError && (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          Feedback alınamadı.{' '}
          <Button variant="link" className="h-auto p-0" onClick={() => void q.refetch()}>
            Tekrar dene
          </Button>
        </div>
      )}

      <AdminTable<FeedbackRow>
        rows={q.data ?? []}
        loading={q.isLoading}
        emptyMessage="Geri bildirim yok"
        getRowKey={(row) => row.id}
        columns={[
          { key: 'created_at', header: 'Zaman', render: (row) => row.created_at },
          { key: 'user', header: 'Kullanıcı', render: (row) => row.username },
          { key: 'type', header: 'Tip', render: (row) => <TypeBadge type={row.type} /> },
          {
            key: 'message',
            header: 'Mesaj',
            className: 'min-w-[320px]',
            render: (row) => (
              <MessageCell
                row={row}
                expanded={expandedIds.has(row.id)}
                onToggle={() => toggleExpanded(row.id)}
              />
            ),
          },
        ]}
      />
    </div>
  )
}

