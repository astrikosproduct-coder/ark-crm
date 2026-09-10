import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

import { api } from '@/lib/api'
import { setCurrentUser, type CurrentUser } from '@/lib/currentUser'

/**
 * The signed-in user, fetched once from /api/auth/me.
 *
 * Deliberately NOT a TanStack Query hook: identity gates whether the rest of
 * the app renders at all, so it must resolve before the first data query runs
 * rather than racing alongside them.
 */

type AuthState =
  | { status: 'loading' }
  | { status: 'signed-out' }
  | { status: 'signed-in'; user: CurrentUser }

interface AuthContextValue {
  state: AuthState
  user: CurrentUser | null
  refresh: () => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

/** Sign-in is a real browser navigation — it leaves the SPA for Microsoft. */
export function startSignIn(): void {
  window.location.assign('/api/auth/login')
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading' })

  async function refresh(): Promise<void> {
    try {
      const response = await api.get<CurrentUser>('/auth/me')
      setCurrentUser(response.data)
      setState({ status: 'signed-in', user: response.data })
    } catch {
      // 401 is the ordinary "not signed in yet" case, not an error worth
      // surfacing — the sign-in screen is the answer to it.
      setCurrentUser(null)
      setState({ status: 'signed-out' })
    }
  }

  async function signOut(): Promise<void> {
    try {
      await api.post('/auth/logout')
    } finally {
      setCurrentUser(null)
      setState({ status: 'signed-out' })
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

  const user = state.status === 'signed-in' ? state.user : null

  return (
    <AuthContext.Provider value={{ state, user, refresh, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}
