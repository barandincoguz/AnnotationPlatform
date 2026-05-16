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
    <header className="relative mb-10 overflow-hidden rounded-xl border border-border/60 bg-card/70 px-6 py-7 shadow-sm">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10"
        style={{
          background:
            'radial-gradient(at 0% 0%, hsl(32 60% 92% / 0.55) 0px, transparent 60%),' +
            'radial-gradient(at 100% 100%, hsl(175 45% 90% / 0.55) 0px, transparent 60%)',
        }}
      />
      <div className="flex items-center gap-6">
        <Avatar
          username={user.username}
          color={user.avatar_color}
          size="lg"
          className="h-16 w-16 text-xl shadow-md"
        />
        <div className="space-y-1.5">
          <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
            Profil · Hesap oluşturuldu: {trDate(createdAt)}
          </p>
          <h1 className="font-display text-5xl font-bold tracking-tight">@{user.username}</h1>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-accent/30 bg-accent/10 px-3 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-accent">
            {roleLabel(user.role)}
          </span>
        </div>
      </div>
    </header>
  )
}
