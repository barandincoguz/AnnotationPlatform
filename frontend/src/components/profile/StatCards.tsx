import { Zap, Flame, Target, Award } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import type { ProfileResponse } from '@/lib/profileSchemas'

const TR_FORMATTER = new Intl.NumberFormat('tr-TR')

interface StatCardsProps {
  profile: ProfileResponse
}

// 4f: each card gets its own semantic color identity so the four
// metrics read as distinct facets of the user's account rather than
// four cells of the same chrome.
const CARD_THEMES = {
  xp: 'border-accent/25 bg-accent/[0.04]',
  streak: 'border-warning/25 bg-warning/[0.04]',
  today: 'border-accent2/25 bg-accent2/[0.04]',
  badges: 'border-success/25 bg-success/[0.04]',
} as const

const ICON_THEMES = {
  xp: 'text-accent bg-accent/12',
  streak: 'text-warning bg-warning/12',
  today: 'text-accent2 bg-accent2/12',
  badges: 'text-success bg-success/12',
} as const

function IconOrb({
  Icon,
  tone,
}: {
  Icon: typeof Zap
  tone: keyof typeof ICON_THEMES
}) {
  return (
    <span
      aria-hidden
      className={`inline-flex h-9 w-9 items-center justify-center rounded-lg ${ICON_THEMES[tone]}`}
    >
      <Icon className="h-5 w-5" />
    </span>
  )
}

export function StatCards({ profile }: StatCardsProps) {
  const { xp, streak, today, badges } = profile
  const targetEnabled = today.daily_target > 0
  const ratio = targetEnabled ? Math.min(today.save / today.daily_target, 1) : 0

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
      {/* XP */}
      <Card className={`lift ${CARD_THEMES.xp}`}>
        <CardContent className="space-y-3 p-5">
          <div className="flex items-center gap-3">
            <IconOrb Icon={Zap} tone="xp" />
            <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              Toplam XP
            </span>
          </div>
          <div className="font-display text-[2.75rem] font-bold tracking-tight tabular-nums text-foreground">
            {TR_FORMATTER.format(xp.total)}
          </div>
        </CardContent>
      </Card>

      {/* Streak */}
      <Card className={`lift ${CARD_THEMES.streak}`}>
        <CardContent className="space-y-3 p-5">
          <div className="flex items-center gap-3">
            <IconOrb Icon={Flame} tone="streak" />
            <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              Streak
            </span>
          </div>
          <div className="font-display text-[2.75rem] font-bold tracking-tight tabular-nums text-foreground">
            {streak.current}
          </div>
          <div className="text-[13px] font-medium text-muted-foreground">
            En uzun: {streak.longest} gün
          </div>
        </CardContent>
      </Card>

      {/* Bugün */}
      <Card className={`lift ${CARD_THEMES.today}`}>
        <CardContent className="space-y-3 p-5">
          <div className="flex items-center gap-3">
            <IconOrb Icon={Target} tone="today" />
            <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              Bugün
            </span>
          </div>
          {targetEnabled ? (
            <>
              <div className="font-display text-[2.75rem] font-bold tracking-tight tabular-nums text-foreground">
                {today.save}/{today.daily_target}
              </div>
              <div
                role="progressbar"
                aria-label={`Günlük hedef: ${today.save} / ${today.daily_target}`}
                aria-valuenow={today.save}
                aria-valuemax={today.daily_target}
                aria-valuemin={0}
                className="h-2 rounded-full bg-muted overflow-hidden"
              >
                <div
                  className={`h-full rounded-full transition-[width] duration-500 ${ratio === 1 ? 'bg-success' : 'bg-accent2'}`}
                  style={{ width: `${Math.round(ratio * 100)}%` }}
                />
              </div>
            </>
          ) : (
            <>
              <div className="font-display text-[2.75rem] font-bold tracking-tight tabular-nums text-foreground">
                {today.save}
              </div>
              <div className="text-[13px] text-muted-foreground">Günlük hedef kapalı</div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Rozetler */}
      <Card className={`lift ${CARD_THEMES.badges}`}>
        <CardContent className="space-y-3 p-5">
          <div className="flex items-center gap-3">
            <IconOrb Icon={Award} tone="badges" />
            <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              Toplam Rozet
            </span>
          </div>
          <div className="font-display text-[2.75rem] font-bold tracking-tight tabular-nums text-foreground">
            {badges.length}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
