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
      <Card>
        <CardContent className="p-4">
          <div className="text-3xl font-semibold">
            <span aria-hidden="true">✨</span> {TR_FORMATTER.format(xp.total)}
          </div>
          <div className="text-xs text-muted-foreground mt-1">Toplam XP</div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4">
          <div className="text-3xl font-semibold">
            <span aria-hidden="true">🔥</span> {streak.current}
          </div>
          <div className="text-xs text-muted-foreground mt-1">Streak</div>
          <div className="text-xs text-muted-foreground">
            En uzun: {streak.longest} gün
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4">
          {targetEnabled ? (
            <>
              <div className="text-3xl font-semibold">
                {today.save}/{today.daily_target}
              </div>
              <div
                role="progressbar"
                aria-valuenow={today.save}
                aria-valuemax={today.daily_target}
                aria-valuemin={0}
                className="mt-2 h-2 rounded-full bg-muted overflow-hidden"
              >
                <div
                  className={ratio === 1 ? 'h-full bg-green-500' : 'h-full bg-primary'}
                  style={{ width: `${Math.round(ratio * 100)}%` }}
                />
              </div>
              <div className="text-xs text-muted-foreground mt-1">Bugün</div>
            </>
          ) : (
            <>
              <div className="text-3xl font-semibold">{today.save}</div>
              <div className="text-xs text-muted-foreground mt-1">Bugün</div>
              <div className="text-xs text-muted-foreground">Günlük hedef kapalı</div>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4">
          <div className="text-3xl font-semibold">
            <span aria-hidden="true">🏆</span> {badges.length}
          </div>
          <div className="text-xs text-muted-foreground mt-1">Toplam Rozet</div>
        </CardContent>
      </Card>
    </div>
  )
}
