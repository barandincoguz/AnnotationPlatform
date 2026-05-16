import type { UserSection } from '@/lib/profileSchemas'

interface ProfileHeaderProps {
  user: UserSection
  createdAt: string
}

function trDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('tr-TR', { day: '2-digit', month: 'long', year: 'numeric' })
}

function roleLabel(role: string): string {
  switch (role) {
    case 'admin': return 'Yönetici'
    default: return 'Bursiyer'
  }
}

export function ProfileHeader({ user, createdAt }: ProfileHeaderProps) {
  return (
    <header className="flex items-center gap-4 mb-6">
      <span
        className="inline-flex h-16 w-16 items-center justify-center rounded-full text-2xl font-semibold text-white"
        style={{ backgroundColor: user.avatar_color ?? '#3b82f6' }}
      >
        {user.username[0]?.toUpperCase() ?? '?'}
      </span>
      <div>
        <h1 className="text-2xl font-semibold">@{user.username}</h1>
        <p className="text-sm text-muted-foreground">
          {roleLabel(user.role)} • Hesap oluşturuldu: {trDate(createdAt)}
        </p>
      </div>
    </header>
  )
}
