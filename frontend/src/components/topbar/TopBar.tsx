import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { BarChart3 } from 'lucide-react'
import { useAuthStore } from '@/stores/authStore'
import { useProfile } from '@/api/queries/profile'
import { useOnlineUsers } from '@/api/queries/users'
import { useUnreadNotifications } from '@/api/queries/notifications'
import { BrandMark } from '@/components/shell/BrandMark'
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
  // Backend returns ALL subscribed users including the requester. The
  // current user's avatar is already rendered by ProfileDropdown to the
  // right, so filter self out of the online list to avoid duplication.
  const onlineUsers = useMemo(() => {
    if (online.isError || !online.data) return []
    return user ? online.data.filter((u) => u.id !== user.id) : online.data
  }, [online.isError, online.data, user])
  const unreadCount = unread.isError ? 0 : (unread.data?.items.length ?? 0)

  return (
    <header
      role="banner"
      className="sticky top-0 z-30 h-16 border-b border-border/70 bg-background/85 backdrop-blur-md px-3 sm:px-4 lg:px-6 grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 sm:gap-4 lg:gap-5"
    >
      <BrandMark subtitle="Bursiyer kütüphanesi" />

      <div
        data-testid="topbar-center"
        className="min-w-0 flex items-center justify-center gap-2 sm:gap-3 lg:gap-5 overflow-x-auto [scrollbar-width:none]"
      >
        <Link
          to="/statistics"
          aria-label="İstatistikler"
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center gap-2 rounded-full border border-border bg-card text-foreground shadow-sm transition-colors hover:border-info/50 hover:text-info focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-info sm:w-auto sm:px-3"
        >
          <BarChart3 aria-hidden className="h-4 w-4 shrink-0" />
          <span className="hidden font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground lg:inline">
            İstatistikler
          </span>
        </Link>
        <XPBadge total={xpTotal} />
        <span aria-hidden className="h-5 w-px bg-border" />
        <StreakCounter current={streakCurrent} longest={streakLongest} />
        <span aria-hidden className="h-5 w-px bg-border" />
        <DailyProgress today={todaySave} target={dailyTarget} />
      </div>

      <div className="ml-auto flex items-center gap-4">
        <div className="hidden md:block max-w-[220px] overflow-hidden">
          <OnlineUsers users={onlineUsers} maxVisible={5} />
        </div>
        {user && (
          <div className="flex-none">
            <ProfileDropdown
              user={{
                id: user.id,
                username: user.username,
                role: user.role,
                avatar_color: user.avatar_color,
              }}
              unreadCount={unreadCount}
            />
          </div>
        )}
      </div>
    </header>
  )
}
