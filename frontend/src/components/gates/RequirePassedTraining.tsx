import { Navigate, Outlet } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

export function RequirePassedTraining() {
  const user = useAuthStore((s) => s.user)
  if (user && !user.has_passed_training) {
    return <Navigate to="/training" replace />
  }
  return <Outlet />
}
