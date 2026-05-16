import type { ReactNode } from 'react'

export interface AdminTableColumn<T> {
  key: string
  header: string
  render: (row: T) => ReactNode
  className?: string
}

export interface AdminTableProps<T> {
  rows: T[]
  columns: AdminTableColumn<T>[]
  getRowKey: (row: T) => string | number
  emptyMessage?: string
  loading?: boolean
  skeletonRowCount?: number
}

export function AdminTable<T>({
  rows, columns, getRowKey,
  emptyMessage = 'Kayıt yok',
  loading = false,
  skeletonRowCount = 5,
}: AdminTableProps<T>) {
  if (loading) {
    return (
      <div className="overflow-x-auto rounded border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50">
            <tr>
              {columns.map((c) => (
                <th key={c.key} scope="col" className={`p-2 text-left font-medium ${c.className ?? ''}`}>
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: skeletonRowCount }).map((_, i) => (
              <tr key={i} data-testid="admin-table-skeleton-row" className="border-t">
                {columns.map((c) => (
                  <td key={c.key} className="p-2">
                    <div className="h-4 w-3/4 animate-pulse rounded bg-muted/60" />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (rows.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
        <span aria-hidden className="font-display text-5xl font-medium text-muted-foreground/20 leading-none">№</span>
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">Boş</p>
        <p className="text-sm text-muted-foreground">{emptyMessage ?? 'Kayıt bulunamadı.'}</p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50">
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col" className={`p-2 text-left font-medium ${c.className ?? ''}`}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={getRowKey(r)} className="border-t hover:bg-muted/30">
              {columns.map((c) => (
                <td key={c.key} className={`p-2 ${c.className ?? ''}`}>
                  {c.render(r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
