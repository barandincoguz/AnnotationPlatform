export const NOTIFICATION_KIND_ICONS: Record<string, string> = {
  badge_unlocked: '🏆',
  training_passed: '🎓',
  training_reset: '🔄',
  admin_announcement: '📢',
  lock_lost: '🔓',
}

export function iconForKind(kind: string): string {
  return NOTIFICATION_KIND_ICONS[kind] ?? '🔔'
}
