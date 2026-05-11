import { Link } from 'react-router-dom'
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent,
  DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu'
import { useLogoutMutation } from '@/api/queries/auth'
import {
  useUnreadNotifications, useMarkAllReadMutation, useMarkReadMutation,
} from '@/api/queries/notifications'
import { iconForKind } from '@/lib/notificationKinds'
import { formatRelativeTr } from '@/lib/formatters'
import type { UserSection } from '@/lib/profileSchemas'

interface ProfileDropdownProps {
  user: UserSection
  unreadCount: number
}

function unreadLabel(count: number): string {
  return count >= 10 ? '9+' : String(count)
}

function Avatar({ user }: { user: UserSection }) {
  return (
    <span
      className="inline-flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold text-white"
      style={{ backgroundColor: user.avatar_color }}
    >
      {user.username[0]?.toUpperCase() ?? '?'}
    </span>
  )
}

export function ProfileDropdown({ user, unreadCount }: ProfileDropdownProps) {
  const unread = useUnreadNotifications()
  const markRead = useMarkReadMutation()
  const markAllRead = useMarkAllReadMutation()
  const logout = useLogoutMutation()

  const top10 = (unread.data?.items ?? []).slice(0, 10)

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label="Profil menüsü"
        className="relative inline-flex outline-none focus-visible:ring-2 ring-primary rounded-full"
      >
        <Avatar user={user} />
        {unreadCount > 0 && (
          <span
            data-testid="unread-dot"
            className="absolute -top-1 -right-1 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold text-white"
          >
            {unreadLabel(unreadCount)}
          </span>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel>
          {user.username} <span className="text-xs text-muted-foreground">• {user.role}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />

        <DropdownMenuLabel className="text-xs uppercase">
          🔔 Bildirimler {unreadCount > 0 && <span>({unreadCount} okunmamış)</span>}
        </DropdownMenuLabel>
        {top10.length === 0 ? (
          <div className="px-2 py-3 text-sm text-muted-foreground">Yeni bildirim yok.</div>
        ) : (
          <ul className="max-h-64 overflow-auto">
            {top10.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className="flex w-full items-start gap-2 px-2 py-2 text-left text-sm hover:bg-muted"
                  onClick={() => markRead.mutate(item.id)}
                  aria-label={`${item.title} bildirimini okundu işaretle`}
                >
                  <span className="text-base">{iconForKind(item.kind)}</span>
                  <div className="flex-1 min-w-0">
                    <div className="truncate" title={item.title}>{item.title}</div>
                    <div className="text-xs text-muted-foreground">
                      {formatRelativeTr(item.created_at)}
                    </div>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
        {top10.length > 0 && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={(e) => { e.preventDefault(); markAllRead.mutate() }}
            >
              Tümünü okundu yap
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link to="/me#notifications">Tümünü Gör</Link>
            </DropdownMenuItem>
          </>
        )}

        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/me">Profilim</Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link to="/help">Yardım</Link>
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={(e) => { e.preventDefault(); logout.mutate() }}
        >
          Çıkış
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
