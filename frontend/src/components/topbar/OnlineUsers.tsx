import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from '@/components/ui/tooltip'
import { Avatar } from '@/components/shell/Avatar'
import type { OnlineUser } from '@/lib/profileSchemas'

interface OnlineUsersProps {
  users: OnlineUser[]
  maxVisible: number
}

/**
 * Topbar online indicator — stack of small avatars for the first N
 * users plus a "+M" chip that opens a popover with the remainder.
 *
 * Accessibility:
 *   - Each visible avatar is wrapped in a real <button> (not a <span>)
 *     so the Radix tooltip fires on keyboard focus as well as hover,
 *     and so the avatar (which is itself aria-hidden) gets an accessible
 *     name via aria-label={username}.
 *   - The overflow chip carries its own aria-label naming how many
 *     additional users are online — "+2" alone is meaningless for AT.
 *
 * Self-filtering happens in the caller (TopBar) so the current user
 * does not duplicate the avatar already shown by ProfileDropdown.
 */
export function OnlineUsers({ users, maxVisible }: OnlineUsersProps) {
  if (users.length === 0) return null

  const visible = users.slice(0, maxVisible)
  const overflow = users.slice(maxVisible)

  return (
    <TooltipProvider delayDuration={200}>
      <div
        // Slight negative spacing produces the "stacked avatars" effect;
        // each Avatar already carries `ring-2 ring-card`, so the rings
        // separate adjacent circles even while they overlap.
        className="inline-flex items-center -space-x-1.5"
        aria-label={`${users.length} kullanıcı çevrimiçi`}
      >
        {visible.map((u) => (
          <Tooltip key={u.id}>
            <TooltipTrigger asChild>
              <button
                type="button"
                aria-label={u.username}
                className="relative rounded-full outline-none transition-transform focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background hover:z-10 hover:scale-110"
              >
                <Avatar username={u.username} color={u.avatar_color} size="sm" />
              </button>
            </TooltipTrigger>
            <TooltipContent sideOffset={8}>{u.username}</TooltipContent>
          </Tooltip>
        ))}
        {overflow.length > 0 && (
          <Popover>
            <PopoverTrigger asChild>
              <button
                type="button"
                aria-label={`Diğer ${overflow.length} çevrimiçi kullanıcı`}
                className="relative inline-flex h-7 min-w-7 items-center justify-center rounded-full border border-border bg-card px-1.5 font-mono text-[11px] font-bold text-foreground/80 ring-2 ring-card shadow-sm transition-colors hover:z-10 hover:border-accent/50 hover:bg-accent/10 hover:text-accent focus-visible:outline-none focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              >
                +{overflow.length}
              </button>
            </PopoverTrigger>
            <PopoverContent className="w-64 p-3" align="end" sideOffset={10}>
              <div className="mb-2.5 flex items-center justify-between">
                <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                  Diğer çevrimiçi
                </span>
                <span className="font-mono text-[11px] font-bold tabular-nums text-foreground/75">
                  {overflow.length}
                </span>
              </div>
              <ul className="space-y-2">
                {overflow.map((u) => (
                  <li key={u.id} className="flex items-center gap-2.5">
                    <Avatar username={u.username} color={u.avatar_color} size="sm" />
                    <span className="text-[14px] font-medium text-foreground">
                      {u.username}
                    </span>
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
