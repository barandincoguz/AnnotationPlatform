import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from '@/components/ui/tooltip'
import type { OnlineUser } from '@/lib/profileSchemas'

interface OnlineUsersProps {
  users: OnlineUser[]
  maxVisible: number
}

function Avatar({ user, size = 'sm' }: { user: OnlineUser; size?: 'sm' | 'md' }) {
  const cls = size === 'sm' ? 'h-6 w-6 text-xs' : 'h-8 w-8 text-sm'
  return (
    <span
      className={`inline-flex items-center justify-center rounded-full font-medium text-white ${cls}`}
      style={{ backgroundColor: user.avatar_color }}
    >
      {user.username[0]?.toUpperCase() ?? '?'}
    </span>
  )
}

export function OnlineUsers({ users, maxVisible }: OnlineUsersProps) {
  if (users.length === 0) return null

  const visible = users.slice(0, maxVisible)
  const overflow = users.length - visible.length

  return (
    <TooltipProvider delayDuration={200}>
      <div
        className="inline-flex items-center gap-1"
        aria-label={`${users.length} kullanıcı çevrimiçi`}
      >
        {visible.map((u) => (
          <Tooltip key={u.id}>
            <TooltipTrigger asChild>
              <span>
                <Avatar user={u} />
              </span>
            </TooltipTrigger>
            <TooltipContent>{u.username}</TooltipContent>
          </Tooltip>
        ))}
        {overflow > 0 && (
          <Popover>
            <PopoverTrigger asChild>
              <button
                type="button"
                className="inline-flex h-6 items-center justify-center rounded-full bg-muted px-2 text-xs font-medium text-muted-foreground hover:bg-muted-foreground/20"
              >
                +{overflow}
              </button>
            </PopoverTrigger>
            <PopoverContent className="w-56" align="end">
              <div className="text-xs font-semibold text-muted-foreground mb-2">
                Çevrimiçi ({users.length})
              </div>
              <ul className="space-y-2">
                {users.map((u) => (
                  <li key={u.id} className="flex items-center gap-2">
                    <Avatar user={u} />
                    <span className="text-sm">{u.username}</span>
                  </li>
                ))}
              </ul>
            </PopoverContent>
          </Popover>
        )}
      </div>
    </TooltipProvider>
  )
}
