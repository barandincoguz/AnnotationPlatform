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
      className={cn(
        isLocked && 'bg-card border-dashed border-muted-foreground/30 opacity-70',
        !isLocked && 'hover:shadow-md transition-shadow',
      )}
      aria-disabled={isLocked || undefined}
    >
      <CardContent className="p-4 space-y-2">
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
          {isLocked ? 'KİLİTLİ' : 'KAZANILMIŞ'}
        </p>
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center justify-center h-6 w-6 rounded-full bg-muted/40" aria-hidden="true">{badgeIcon(badge.id)}</span>
          <div className="flex-1">
            <h3 className={cn(
              'font-display font-medium leading-tight',
              isLocked && 'text-muted-foreground',
            )}>
              {badge.name}
            </h3>
          </div>
          {isLocked && (
            <Lock className="h-4 w-4 text-muted-foreground flex-shrink-0" aria-label="Kilitli" />
          )}
        </div>

        {body && (
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <p className={cn(
                  'line-clamp-2 text-sm',
                  isLocked ? 'text-muted-foreground/70' : 'text-muted-foreground',
                )}>
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
