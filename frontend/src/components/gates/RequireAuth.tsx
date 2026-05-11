import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

export function RequireAuth() {
  const status = useAuthStore((s) => s.status)
  const location = useLocation()

  if (status === 'anon') {
    return <Navigate to="/login" replace state={{ from: location }} />
  }
  // status==='authed' OR (loading/error — App's LoadingScreen is rendered
  // OUTSIDE the route tree, so by the time this gate runs we are authed).
  return <Outlet />
}
