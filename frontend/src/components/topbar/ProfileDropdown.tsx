import { Link } from 'react-router-dom'
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent,
  DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu'
import { Avatar } from '@/components/shell/Avatar'
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
        className="relative inline-flex outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-full transition-transform hover:scale-[1.03]"
      >
        <Avatar username={user.username} color={user.avatar_color} size="md" />
        {unreadCount > 0 && (
          <span
            data-testid="unread-dot"
            className="absolute -top-1.5 -right-1.5 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1.5 text-[11px] font-bold text-destructive-foreground shadow-sm ring-2 ring-background"
          >
            {unreadLabel(unreadCount)}
          </span>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        sideOffset={12}
        className="w-[22rem] border-border/70 shadow-xl shadow-foreground/5"
      >
        <DropdownMenuLabel className="px-3.5 pb-3 pt-3.5">
          <div className="flex items-center gap-3">
            <Avatar username={user.username} color={user.avatar_color} size="lg" />
            <div className="min-w-0">
              <div className="font-display text-[17px] font-bold tracking-tight truncate">
                {user.username}
              </div>
              <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground mt-0.5">
                {user.role === 'admin' ? 'Yönetici' : 'Bursiyer'}
              </div>
            </div>
          </div>
        </DropdownMenuLabel>

        <DropdownMenuSeparator />

        <DropdownMenuLabel className="flex items-center justify-between px-3.5 py-2.5 font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          <span>Bildirimler</span>
          {unreadCount > 0 && (
            <span className="text-destructive normal-case font-sans font-semibold tracking-normal">
              {unreadCount} okunmamış
            </span>
          )}
        </DropdownMenuLabel>
        {top10.length === 0 ? (
          <div className="px-3.5 py-5 text-center text-[15px] text-muted-foreground">
            <span aria-hidden className="block text-3xl opacity-30 mb-1">·</span>
            Yeni bildirim yok.
          </div>
        ) : (
          <ul className="max-h-72 overflow-auto">
            {top10.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className="flex w-full items-start gap-3 px-3.5 py-3 text-left text-[15px] transition-colors hover:bg-muted focus-visible:bg-muted focus-visible:outline-none"
                  onClick={() => markRead.mutate(item.id)}
                  aria-label={`${item.title} bildirimini okundu işaretle`}
                >
                  <span className="text-lg leading-none mt-0.5" aria-hidden>
                    {iconForKind(item.kind)}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="truncate font-semibold" title={item.title}>
                      {item.title}
                    </div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground/80 mt-1">
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
              className="text-[15px] font-medium"
            >
              Tümünü okundu yap
            </DropdownMenuItem>
            <DropdownMenuItem asChild className="text-[15px] font-medium">
              <Link to="/me#notifications">
                Tümünü Gör
                <span aria-hidden className="ml-auto text-accent font-bold">→</span>
              </Link>
            </DropdownMenuItem>
          </>
        )}

        <DropdownMenuSeparator />
        <DropdownMenuItem asChild className="text-[15px] font-medium">
          <Link to="/me">
            Profilim
            <span aria-hidden className="ml-auto text-muted-foreground/60">↗</span>
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild className="text-[15px] font-medium">
          <Link to="/help">
            Yardım
            <span aria-hidden className="ml-auto text-muted-foreground/60">?</span>
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={(e) => { e.preventDefault(); logout.mutate() }}
          className="text-[15px] font-medium text-destructive focus:text-destructive focus:bg-destructive/10"
        >
          Çıkış
          <span aria-hidden className="ml-auto opacity-60">⎋</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
