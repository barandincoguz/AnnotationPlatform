import { formatRelativeTr } from '@/lib/formatters'

interface AttributionLabelProps {
  username: string | null
  date: string | null
}

export function AttributionLabel({ username, date }: AttributionLabelProps) {
  if (!username) return <span className="text-muted-foreground">-</span>
  return (
    <span className="text-xs text-muted-foreground">
      {username} · {formatRelativeTr(date)}
    </span>
  )
}
