import { create } from 'zustand'

export type AuthStatus = 'loading' | 'authed' | 'anon' | 'error'

export interface User {
  id: number
  username: string
  email: string | null
  role: 'user' | 'admin'
  is_active: boolean
  has_seen_manual: boolean
  has_passed_training: boolean
  avatar_color: string | null
  created_at: string
}

interface AuthState {
  status: AuthStatus
  user: User | null
  error: string | null
  setUser: (user: User) => void
  setError: (message: string) => void
  setStatus: (status: AuthStatus) => void
  clear: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  status: 'loading',
  user: null,
  error: null,
  setUser: (user) => set({ status: 'authed', user, error: null }),
  setError: (message) => set({ status: 'error', error: message }),
  setStatus: (status) => set({ status }),
  clear: () => set({ status: 'anon', user: null, error: null }),
}))

export const selectUser = (s: AuthState) => s.user
export const selectIsAuthed = (s: AuthState) => s.status === 'authed'
export const selectIsAdmin = (s: AuthState) => s.user?.role === 'admin'
