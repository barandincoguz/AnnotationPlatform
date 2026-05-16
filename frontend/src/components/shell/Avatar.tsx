import { cn } from '@/lib/utils'

interface AvatarProps {
  username: string
  /** Hex color string, may be null/undefined. Falls back to theme token. */
  color?: string | null
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const SIZE_MAP = {
  sm: 'h-7 w-7 text-xs',
  md: 'h-9 w-9 text-sm',
  lg: 'h-12 w-12 text-base',
} as const

/**
 * Avatar — username initial on a colored circle. Single source for the
 * fallback color used when the user has no `avatar_color` set. The
 * fallback resolves via CSS var (--avatar-fallback) so theme refreshes
 * propagate automatically instead of needing to touch each call site.
 */
export function Avatar({ username, color, size = 'md', className }: AvatarProps) {
  const bg = color && color.trim().length > 0 ? color : 'hsl(var(--avatar-fallback))'
  const initial = username[0]?.toUpperCase() ?? '?'
  return (
    <span
      aria-hidden
      style={{ backgroundColor: bg }}
      className={cn(
        'inline-flex items-center justify-center rounded-full font-semibold text-white shadow-sm ring-2 ring-card',
        SIZE_MAP[size],
        className,
      )}
    >
      {initial}
    </span>
  )
}
