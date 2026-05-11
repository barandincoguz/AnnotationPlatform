import { type ReactNode } from 'react'
import { useAuthStore } from '@/stores/authStore'

interface Props {
  children: ReactNode
}

export function RequireAdmin({ children }: Props) {
  const isAdmin = useAuthStore((s) => s.user?.role === 'admin')
  if (!isAdmin) {
    // Existence-hide: render the 404 surface instead of redirecting,
    // matching the backend's policy that non-admins never learn /admin/* exists.
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3">
        <p className="text-lg font-medium">Sayfa bulunamadı</p>
      </div>
    )
  }
  return <>{children}</>
}
