import { Lock } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { formatRelativeTr } from '@/lib/formatters'

const BADGE_ICONS: Record<string, string> = {
  first_annotation: '🏆',
  annotations_10: '✨',
  annotations_100: '💪',
  annotations_1000: '🌟',
  first_completion: '✅',
  marathoner: '🏃',
  good_reviewer: '🛡️',
}

function badgeIcon(id: string): string {
  return BADGE_ICONS[id] ?? '🎖️'
}

interface BadgeCardProps {
  badge: {
    id: string
    name: string
    description: string
    criterion?: string | null
    earned_at?: string
  }
  variant: 'earned' | 'locked'
}

export function BadgeCard({ badge, variant }: BadgeCardProps) {
  const isLocked = variant === 'locked'
  const body = isLocked ? (badge.criterion ?? '') : badge.description

  return (
    <Card
      className={cn(isLocked && 'grayscale opacity-60')}
      aria-disabled={isLocked || undefined}
    >
      <CardContent className="p-4 space-y-2">
        <div className="flex items-center gap-2">
          <span className="text-2xl" aria-hidden="true">{badgeIcon(badge.id)}</span>
          <h3 className="font-medium leading-tight">{badge.name}</h3>
          {isLocked && (
            <Lock className="ml-auto h-4 w-4 text-muted-foreground" aria-label="Kilitli" />
          )}
        </div>

        {body && (
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <p className="line-clamp-2 text-sm text-muted-foreground">
                  {body}
                </p>
              </TooltipTrigger>
              <TooltipContent>{body}</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}

        {!isLocked && badge.earned_at && (
          <span className="block text-xs text-muted-foreground">
            {formatRelativeTr(badge.earned_at)}
          </span>
        )}
      </CardContent>
    </Card>
  )
}
