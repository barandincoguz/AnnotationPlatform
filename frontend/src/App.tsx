import { lazy, Suspense, useEffect, useState } from 'react'
import { useNavigate, Route, Routes, Navigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { client, setNavigator, setAuthHandlers, markHydrated } from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { authKeys } from '@/api/queries/auth'
import { LoadingScreen } from '@/components/shell/LoadingScreen'
import { RouteLoading } from '@/components/shell/RouteLoading'
import { RequireAuth } from '@/components/gates/RequireAuth'
import { RequireSeenManual } from '@/components/gates/RequireSeenManual'
import { RequirePassedTraining } from '@/components/gates/RequirePassedTraining'
import { RequireAdmin } from '@/components/gates/RequireAdmin'

const Login = lazy(() => import('@/routes/Login').then((m) => ({ default: m.Login })))
const Register = lazy(() => import('@/routes/Register').then((m) => ({ default: m.Register })))
const NotFound = lazy(() => import('@/routes/NotFound').then((m) => ({ default: m.NotFound })))
const Annotate = lazy(() => import('@/routes/Annotate').then((m) => ({ default: m.Annotate })))
const AnnotateLayout = lazy(() =>
  import('@/routes/AnnotateLayout').then((m) => ({ default: m.AnnotateLayout })),
)
const AnnotateDoc = lazy(() =>
  import('@/routes/AnnotateDoc').then((m) => ({ default: m.AnnotateDoc })),
)
const Profile = lazy(() => import('@/routes/Profile').then((m) => ({ default: m.Profile })))
const Help = lazy(() => import('@/routes/Help').then((m) => ({ default: m.Help })))
const Training = lazy(() => import('@/routes/Training').then((m) => ({ default: m.Training })))
const AppShell = lazy(() =>
  import('@/components/shell/AppShell').then((m) => ({ default: m.AppShell })),
)
const AdminLayout = lazy(() =>
  import('@/routes/admin/AdminLayout').then((m) => ({ default: m.AdminLayout })),
)
const AuditPage = lazy(() =>
  import('@/routes/admin/AuditPage').then((m) => ({ default: m.AuditPage })),
)
const EventsPage = lazy(() =>
  import('@/routes/admin/EventsPage').then((m) => ({ default: m.EventsPage })),
)
const LocksPage = lazy(() =>
  import('@/routes/admin/LocksPage').then((m) => ({ default: m.LocksPage })),
)
const UsersPage = lazy(() =>
  import('@/routes/admin/UsersPage').then((m) => ({ default: m.UsersPage })),
)
const SettingsPage = lazy(() =>
  import('@/routes/admin/SettingsPage').then((m) => ({ default: m.SettingsPage })),
)
const GoldDocsPage = lazy(() =>
  import('@/routes/admin/training/GoldDocsPage').then((m) => ({ default: m.GoldDocsPage })),
)
const QuizPage = lazy(() =>
  import('@/routes/admin/training/QuizPage').then((m) => ({ default: m.QuizPage })),
)
const MirrorHealthPage = lazy(() =>
  import('@/routes/admin/MirrorHealthPage').then((m) => ({ default: m.MirrorHealthPage })),
)
const BackupPage = lazy(() =>
  import('@/routes/admin/BackupPage').then((m) => ({ default: m.BackupPage })),
)
const RetentionPage = lazy(() =>
  import('@/routes/admin/RetentionPage').then((m) => ({ default: m.RetentionPage })),
)

export default function App() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [retryNonce, setRetryNonce] = useState(0)

  useEffect(() => setNavigator(navigate), [navigate])
  useEffect(() => {
    setAuthHandlers({
      onSessionExpired: () => useAuthStore.getState().clear(),
    })
  }, [])

  // Hydration effect: runs on mount AND whenever retryNonce bumps.
  // qc is provider-stable; including it in deps is defensive.
  useEffect(() => {
    const ctrl = new AbortController()
    let cancelled = false
    void (async () => {
      try {
        const result = await client.GET('/api/auth/me', { signal: ctrl.signal })
        if (cancelled) return
        if (result.error !== undefined || result.response.status === 401) {
          useAuthStore.getState().clear()
        } else if (result.data) {
          const user = result.data
          useAuthStore.getState().setUser(user)
          qc.setQueryData(authKeys.me, user) // PRIME cache to skip duplicate /me fetch
        } else {
          // Unexpected: no data and no error — treat as anon to be safe.
          useAuthStore.getState().clear()
        }
        markHydrated()
      } catch (e: unknown) {
        if (cancelled) return
        if (
          typeof e === 'object' &&
          e !== null &&
          'name' in e &&
          (e as { name?: unknown }).name === 'AbortError'
        )
          return
        const message = e instanceof Error ? e.message : String(e)
        useAuthStore.getState().setError(message)
        // markHydrated() NOT called on network error — retry-safe.
      }
    })()
    return () => {
      cancelled = true
      ctrl.abort()
    }
  }, [qc, retryNonce])

  const status = useAuthStore((s) => s.status)
  const handleRetry = () => {
    useAuthStore.getState().setStatus('loading') // flip out of 'error' for UI feedback
    setRetryNonce((n) => n + 1) // re-fire hydration effect
  }

  if (status === 'loading') return <LoadingScreen />
  if (status === 'error') return <LoadingScreen mode="error" onRetry={handleRetry} />

  return (
    <Suspense fallback={<RouteLoading />}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        <Route element={<RequireAuth />}>
          <Route path="/help" element={<Help />} />

          <Route element={<RequireSeenManual />}>
            <Route path="/training" element={<Training />} />

            <Route element={<RequirePassedTraining />}>
              <Route element={<AppShell />}>
                <Route element={<AnnotateLayout />}>
                  <Route path="/" element={<Annotate />} />
                  <Route path="/docs/:docId" element={<AnnotateDoc />} />
                </Route>
                <Route path="/me" element={<Profile />} />
              </Route>
            </Route>
          </Route>

          <Route
            path="/admin"
            element={
              <RequireAdmin>
                <AdminLayout />
              </RequireAdmin>
            }
          >
            <Route index element={<Navigate to="/admin/audit" replace />} />
            <Route path="audit" element={<AuditPage />} />
            <Route path="events" element={<EventsPage />} />
            <Route path="locks" element={<LocksPage />} />
            <Route path="users" element={<UsersPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="training/gold-docs" element={<GoldDocsPage />} />
            <Route path="training/quiz" element={<QuizPage />} />
            <Route path="mirror" element={<MirrorHealthPage />} />
            <Route path="backup" element={<BackupPage />} />
            <Route path="retention" element={<RetentionPage />} />
          </Route>
        </Route>

        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  )
}
