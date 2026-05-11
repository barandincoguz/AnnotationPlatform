import { describe, it, expect, beforeEach } from 'vitest'
import { useAuthStore, selectUser, selectIsAuthed, selectIsAdmin, type User } from './authStore'

const makeUser = (overrides: Partial<User> = {}): User => ({
  id: 1,
  username: 'tester',
  email: 'tester@example.com',
  role: 'user',
  is_active: true,
  has_seen_manual: true,
  has_passed_training: true,
  avatar_color: '#3b82f6',
  created_at: '2026-05-01T00:00:00+00:00',
  ...overrides,
})

beforeEach(() => {
  useAuthStore.setState({ status: 'loading', user: null, error: null })
})

describe('authStore transitions', () => {
  it('defaults to loading/null/null on first import', () => {
    const s = useAuthStore.getState()
    expect(s.status).toBe('loading')
    expect(s.user).toBeNull()
    expect(s.error).toBeNull()
  })

  it('setUser → authed + clears error', () => {
    useAuthStore.setState({ status: 'error', error: 'previous fail' })
    useAuthStore.getState().setUser(makeUser())
    const s = useAuthStore.getState()
    expect(s.status).toBe('authed')
    expect(s.user?.username).toBe('tester')
    expect(s.error).toBeNull()
  })

  it('setError → error + keeps existing user untouched (renders LoadingScreen anyway)', () => {
    useAuthStore.setState({ status: 'authed', user: makeUser(), error: null })
    useAuthStore.getState().setError('network down')
    const s = useAuthStore.getState()
    expect(s.status).toBe('error')
    expect(s.error).toBe('network down')
  })

  it('setStatus("loading") flips status without altering user/error (used by retry)', () => {
    useAuthStore.setState({ status: 'error', error: 'fail', user: null })
    useAuthStore.getState().setStatus('loading')
    expect(useAuthStore.getState().status).toBe('loading')
    expect(useAuthStore.getState().error).toBe('fail') // not cleared
  })

  it('clear → anon + null user/error (used by logout AND 401 anon)', () => {
    useAuthStore.setState({ status: 'authed', user: makeUser(), error: null })
    useAuthStore.getState().clear()
    const s = useAuthStore.getState()
    expect(s.status).toBe('anon')
    expect(s.user).toBeNull()
    expect(s.error).toBeNull()
  })
})

describe('authStore selectors', () => {
  it('selectUser', () => {
    useAuthStore.getState().setUser(makeUser({ username: 'alice' }))
    expect(selectUser(useAuthStore.getState())?.username).toBe('alice')
  })

  it('selectIsAuthed is true only on status==="authed"', () => {
    useAuthStore.setState({ status: 'loading' })
    expect(selectIsAuthed(useAuthStore.getState())).toBe(false)
    useAuthStore.getState().setUser(makeUser())
    expect(selectIsAuthed(useAuthStore.getState())).toBe(true)
    useAuthStore.getState().clear()
    expect(selectIsAuthed(useAuthStore.getState())).toBe(false)
  })

  it('selectIsAdmin reflects user.role', () => {
    useAuthStore.getState().setUser(makeUser({ role: 'user' }))
    expect(selectIsAdmin(useAuthStore.getState())).toBe(false)
    useAuthStore.getState().setUser(makeUser({ role: 'admin' }))
    expect(selectIsAdmin(useAuthStore.getState())).toBe(true)
  })
})
