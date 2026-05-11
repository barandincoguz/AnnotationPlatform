import { Navigate, Outlet } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

export function RequireSeenManual() {
  const user = useAuthStore((s) => s.user)
  if (user && !user.has_seen_manual) {
    return <Navigate to="/help?first_time=true" replace />
  }
  return <Outlet />
}
