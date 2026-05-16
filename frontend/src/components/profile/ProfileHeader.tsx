import { Avatar } from '@/components/shell/Avatar'
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
    <header className="flex items-center gap-5 mb-8">
      <Avatar username={user.username} color={user.avatar_color} size="lg" />
      <div className="space-y-0.5">
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
          Profil · Hesap oluşturuldu: {trDate(createdAt)}
        </p>
        <h1 className="font-display text-4xl tracking-tight">@{user.username}</h1>
        <span className="inline-block mt-1 rounded-full border border-border bg-secondary px-2.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.18em] text-secondary-foreground">
          {roleLabel(user.role)}
        </span>
      </div>
    </header>
  )
}
