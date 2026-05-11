import { useAuthStore } from '@/stores/authStore'
import { useProfile } from '@/api/queries/profile'
import { ProfileHeader } from '@/components/profile/ProfileHeader'
import { StatCards } from '@/components/profile/StatCards'
import { BadgesGrid } from '@/components/badges/BadgesGrid'
import { NotificationsList } from '@/components/notifications/NotificationsList'

export function Profile() {
  const user = useAuthStore((s) => s.user)
  const profile = useProfile()

  if (profile.isError) {
    return (
      <div className="mx-auto max-w-4xl p-6">
        <p className="text-sm text-amber-600">
          Profil yüklenemedi.{' '}
          <button
            type="button"
            className="underline"
            onClick={() => profile.refetch()}
          >
            Yeniden dene
          </button>
        </p>
      </div>
    )
  }

  if (profile.isPending || !profile.data || !user) {
    return (
      <div className="mx-auto max-w-4xl p-6">
        <div className="h-16 w-48 animate-pulse rounded bg-muted mb-6" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded bg-muted" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl p-6 space-y-8">
      <ProfileHeader user={profile.data.user} createdAt={user.created_at} />
      <StatCards profile={profile.data} />
      <BadgesGrid />
      <NotificationsList />
    </div>
  )
}
