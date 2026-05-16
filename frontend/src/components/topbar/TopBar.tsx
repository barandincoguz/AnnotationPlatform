import { Link } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useProfile } from '@/api/queries/profile'
import { useOnlineUsers } from '@/api/queries/users'
import { useUnreadNotifications } from '@/api/queries/notifications'
import { XPBadge } from './XPBadge'
import { StreakCounter } from './StreakCounter'
import { DailyProgress } from './DailyProgress'
import { OnlineUsers } from './OnlineUsers'
import { ProfileDropdown } from './ProfileDropdown'

export function TopBar() {
  const user = useAuthStore((s) => s.user)
  const profile = useProfile()
  const online = useOnlineUsers()
  const unread = useUnreadNotifications()

  const xpTotal = profile.data?.xp.total ?? 0
  const streakCurrent = profile.data?.streak.current ?? 0
  const streakLongest = profile.data?.streak.longest ?? 0
  const todaySave = profile.data?.today.save ?? 0
  const dailyTarget = profile.data?.today.daily_target ?? 0
  const onlineUsers = online.isError ? [] : (online.data ?? [])
  const unreadCount = unread.isError ? 0 : (unread.data?.items.length ?? 0)

  return (
    <header
      role="banner"
      className="sticky top-0 z-30 h-14 border-b border-border/70 bg-background/85 backdrop-blur-md px-5 grid grid-cols-[1fr_auto_1fr] items-center gap-4"
    >
      <Link
        to="/"
        aria-label="Ana sayfaya dön"
        className="group inline-flex items-center gap-3 outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-md w-fit transition-opacity"
      >
        <span
          aria-hidden
          className="grid h-8 w-8 place-items-center rounded-md border border-border bg-card font-display text-base font-semibold text-foreground transition-colors group-hover:border-accent group-hover:text-accent"
        >
          A
        </span>
        <span className="flex flex-col leading-tight">
          <span className="font-display text-[15px] font-semibold tracking-tight text-foreground">
            Anotasyon Platformu
          </span>
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            Bursiyer kütüphanesi
          </span>
        </span>
      </Link>

      <div className="flex items-center gap-5">
        <XPBadge total={xpTotal} />
        <span aria-hidden className="h-4 w-px bg-border" />
        <StreakCounter current={streakCurrent} longest={streakLongest} />
        <span aria-hidden className="h-4 w-px bg-border" />
        <DailyProgress today={todaySave} target={dailyTarget} />
      </div>

      <div className="ml-auto flex items-center gap-4">
        <div className="hidden md:block max-w-[200px] overflow-hidden">
          <OnlineUsers users={onlineUsers} maxVisible={5} />
        </div>
        {user && (
          <div className="flex-none">
            <ProfileDropdown
              user={{
                id: user.id,
                username: user.username,
                role: user.role,
                avatar_color: user.avatar_color ?? '#3b82f6',
              }}
              unreadCount={unreadCount}
            />
          </div>
        )}
      </div>
    </header>
  )
}
