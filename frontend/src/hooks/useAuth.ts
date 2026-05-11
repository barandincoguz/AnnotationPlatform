import { useAuthStore, selectIsAuthed, selectIsAdmin } from '@/stores/authStore'
import { useLoginMutation, useRegisterMutation, useLogoutMutation } from '@/api/queries/auth'

export function useAuth() {
  const status = useAuthStore((s) => s.status)
  const user = useAuthStore((s) => s.user)
  const error = useAuthStore((s) => s.error)
  const isAuthed = useAuthStore(selectIsAuthed)
  const isAdmin = useAuthStore(selectIsAdmin)

  const loginMutation = useLoginMutation()
  const registerMutation = useRegisterMutation()
  const logoutMutation = useLogoutMutation()

  return {
    status,
    user,
    error,
    isAuthed,
    isAdmin,
    loginMutation,
    registerMutation,
    logoutMutation,
  }
}
