import { useEffect, useState } from 'react'
import { useNavigate, Route, Routes } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { client, setNavigator, setAuthHandlers, markHydrated } from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { authKeys } from '@/api/queries/auth'
import { LoadingScreen } from '@/components/shell/LoadingScreen'
import { AppShell } from '@/components/shell/AppShell'
import { RequireAuth } from '@/components/gates/RequireAuth'
import { RequireSeenManual } from '@/components/gates/RequireSeenManual'
import { RequirePassedTraining } from '@/components/gates/RequirePassedTraining'
import { RequireAdmin } from '@/components/gates/RequireAdmin'
import { Login } from '@/routes/Login'
import { Register } from '@/routes/Register'
import { NotFound } from '@/routes/NotFound'
import { Annotate } from '@/routes/Annotate'
import { Profile } from '@/routes/Profile'
import { Help } from '@/routes/Help'
import { Training } from '@/routes/Training'
import { AdminLayout } from '@/routes/admin/AdminLayout'

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
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      <Route element={<RequireAuth />}>
        <Route path="/help" element={<Help />} />

        <Route element={<RequireSeenManual />}>
          <Route path="/training" element={<Training />} />

          <Route element={<RequirePassedTraining />}>
            <Route element={<AppShell />}>
              <Route path="/" element={<Annotate />} />
              <Route path="/me" element={<Profile />} />
            </Route>
          </Route>
        </Route>

        <Route
          path="/admin/*"
          element={
            <RequireAdmin>
              <AdminLayout />
            </RequireAdmin>
          }
        />
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}
