import { Zap, Flame, Target, Award } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import type { ProfileResponse } from '@/lib/profileSchemas'

const TR_FORMATTER = new Intl.NumberFormat('tr-TR')

interface StatCardsProps {
  profile: ProfileResponse
}

export function StatCards({ profile }: StatCardsProps) {
  const { xp, streak, today, badges } = profile
  const targetEnabled = today.daily_target > 0
  const ratio = targetEnabled ? Math.min(today.save / today.daily_target, 1) : 0

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      {/* XP */}
      <Card className="hover:shadow-sm transition-shadow">
        <CardContent className="p-4">
          <div className="flex items-center gap-1.5 mb-2">
            <Zap aria-hidden="true" className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-muted-foreground">Toplam XP</span>
          </div>
          <div className="font-display text-4xl font-medium tracking-tight tabular-nums">
            {TR_FORMATTER.format(xp.total)}
          </div>
        </CardContent>
      </Card>

      {/* Streak */}
      <Card className="hover:shadow-sm transition-shadow">
        <CardContent className="p-4">
          <div className="flex items-center gap-1.5 mb-2">
            <Flame aria-hidden="true" className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-muted-foreground">Streak</span>
          </div>
          <div className="font-display text-4xl font-medium tracking-tight tabular-nums">
            {streak.current}
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            En uzun: {streak.longest} gün
          </div>
        </CardContent>
      </Card>

      {/* Bugün */}
      <Card className="hover:shadow-sm transition-shadow">
        <CardContent className="p-4">
          <div className="flex items-center gap-1.5 mb-2">
            <Target aria-hidden="true" className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-muted-foreground">Bugün</span>
          </div>
          {targetEnabled ? (
            <>
              <div className="font-display text-4xl font-medium tracking-tight tabular-nums">
                {today.save}/{today.daily_target}
              </div>
              <div
                role="progressbar"
                aria-valuenow={today.save}
                aria-valuemax={today.daily_target}
                aria-valuemin={0}
                className="mt-2 h-1.5 rounded-full bg-muted overflow-hidden"
              >
                <div
                  className={ratio === 1 ? 'h-full rounded-full bg-success' : 'h-full rounded-full bg-primary'}
                  style={{ width: `${Math.round(ratio * 100)}%` }}
                />
              </div>
            </>
          ) : (
            <>
              <div className="font-display text-4xl font-medium tracking-tight tabular-nums">
                {today.save}
              </div>
              <div className="text-xs text-muted-foreground mt-1">Günlük hedef kapalı</div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Rozetler */}
      <Card className="hover:shadow-sm transition-shadow">
        <CardContent className="p-4">
          <div className="flex items-center gap-1.5 mb-1">
            <Award aria-hidden="true" className="h-3.5 w-3.5 text-muted-foreground" />
          </div>
          <div className="font-display text-4xl font-medium tracking-tight tabular-nums">
            {badges.length}
          </div>
          <div className="font-mono text-[9px] uppercase tracking-[0.22em] text-muted-foreground mt-1">Toplam Rozet</div>
        </CardContent>
      </Card>
    </div>
  )
}
