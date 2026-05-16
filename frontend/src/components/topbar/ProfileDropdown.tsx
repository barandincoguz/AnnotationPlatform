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
      className="inline-flex h-9 w-9 items-center justify-center rounded-full text-sm font-semibold text-white ring-2 ring-card shadow-sm transition-shadow hover:shadow-md"
      style={{ backgroundColor: user.avatar_color ?? '#3b82f6' }}
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
        className="relative inline-flex outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-full"
      >
        <Avatar user={user} />
        {unreadCount > 0 && (
          <span
            data-testid="unread-dot"
            className="absolute -top-1 -right-1 inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-accent px-1 text-[10px] font-semibold text-accent-foreground shadow-sm"
          >
            {unreadLabel(unreadCount)}
          </span>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        sideOffset={10}
        className="w-80 border-border/70 shadow-xl shadow-foreground/5"
      >
        <DropdownMenuLabel className="px-3 pb-3 pt-3">
          <div className="flex items-center gap-3">
            <Avatar user={user} />
            <div className="min-w-0">
              <div className="font-display text-sm font-semibold tracking-tight truncate">
                {user.username}
              </div>
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                {user.role === 'admin' ? 'Yönetici' : 'Bursiyer'}
              </div>
            </div>
          </div>
        </DropdownMenuLabel>

        <DropdownMenuSeparator />

        <DropdownMenuLabel className="flex items-center justify-between px-3 py-2 font-mono text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
          <span>Bildirimler</span>
          {unreadCount > 0 && (
            <span className="text-accent normal-case font-sans tracking-normal">
              {unreadCount} okunmamış
            </span>
          )}
        </DropdownMenuLabel>
        {top10.length === 0 ? (
          <div className="px-3 py-4 text-center text-sm text-muted-foreground">
            <span aria-hidden className="block text-2xl opacity-30">·</span>
            Yeni bildirim yok.
          </div>
        ) : (
          <ul className="max-h-64 overflow-auto">
            {top10.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className="flex w-full items-start gap-3 px-3 py-2.5 text-left text-sm transition-colors hover:bg-muted focus-visible:bg-muted focus-visible:outline-none"
                  onClick={() => markRead.mutate(item.id)}
                  aria-label={`${item.title} bildirimini okundu işaretle`}
                >
                  <span className="text-base leading-none mt-0.5" aria-hidden>
                    {iconForKind(item.kind)}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="truncate font-medium" title={item.title}>
                      {item.title}
                    </div>
                    <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/80 mt-0.5">
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
              className="text-sm"
            >
              Tümünü okundu yap
            </DropdownMenuItem>
            <DropdownMenuItem asChild className="text-sm">
              <Link to="/me#notifications">
                Tümünü Gör
                <span aria-hidden className="ml-auto text-accent">→</span>
              </Link>
            </DropdownMenuItem>
          </>
        )}

        <DropdownMenuSeparator />
        <DropdownMenuItem asChild className="text-sm">
          <Link to="/me">
            Profilim
            <span aria-hidden className="ml-auto text-muted-foreground/50">↗</span>
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild className="text-sm">
          <Link to="/help">
            Yardım
            <span aria-hidden className="ml-auto text-muted-foreground/50">?</span>
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={(e) => { e.preventDefault(); logout.mutate() }}
          className="text-sm text-destructive focus:text-destructive focus:bg-destructive/10"
        >
          Çıkış
          <span aria-hidden className="ml-auto opacity-60">⎋</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
