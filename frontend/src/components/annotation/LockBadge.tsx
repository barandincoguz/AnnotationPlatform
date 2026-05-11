import { Lock } from 'lucide-react'

interface LockBadgeProps {
  username: string
  acquiredAt: string
}

export function LockBadge({ username, acquiredAt }: LockBadgeProps) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs"
      title={`Kilit alındı: ${new Date(acquiredAt).toLocaleString('tr-TR')}`}
    >
      <Lock aria-label="kilitli" className="h-3 w-3" />
      <span>{username}</span>
    </span>
  )
}
