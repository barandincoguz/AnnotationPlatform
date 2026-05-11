import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { client, unwrap, unwrapVoid } from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import type { components } from '@/api/types'

type User = components['schemas']['UserOut']
type RegisterInput = components['schemas']['RegisterRequest']
type LoginInput = components['schemas']['LoginRequest']

export const authKeys = {
  me: ['auth', 'me'] as const,
}

export function useMe() {
  const status = useAuthStore((s) => s.status)
  return useQuery({
    queryKey: authKeys.me,
    queryFn: async ({ signal }) => unwrap(await client.GET('/api/auth/me', { signal })),
    enabled: status !== 'anon' && status !== 'loading',
    refetchOnWindowFocus: true,
    staleTime: 60_000,
  })
}

export function useLoginMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (input: LoginInput): Promise<User> => {
      await unwrapVoid(await client.POST('/api/auth/login', { body: input }))
      // Backend returns {ok:true}; pull user via second /me call.
      return unwrap(await client.GET('/api/auth/me'))
    },
    onSuccess: (user) => {
      useAuthStore.getState().setUser(user)
      qc.setQueryData(authKeys.me, user)
    },
  })
}

export function useRegisterMutation() {
  const navigate = useNavigate()
  return useMutation({
    mutationFn: async (input: RegisterInput): Promise<User> =>
      // Backend /api/auth/register returns UserOut (201) but does NOT
      // establish a session cookie. Treat as "create account, log in next".
      unwrap(await client.POST('/api/auth/register', { body: input })),
    onSuccess: () => {
      toast.success('Hesabınız oluşturuldu. Lütfen giriş yapın.')
      navigate('/login')
    },
  })
}

export function useLogoutMutation() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => unwrapVoid(await client.POST('/api/auth/logout')),
    onSuccess: async () => {
      await qc.cancelQueries()
      qc.clear()
      useAuthStore.getState().clear()
      navigate('/login')
    },
  })
}
