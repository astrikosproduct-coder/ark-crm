import axios from 'axios'

// All data access goes through this client, MSW intercepts every request —
// no component may read the Zustand data store directly.
export const api = axios.create({
  baseURL: '/api',

  // An array parameter repeats its name — `?account_type=A&account_type=B` —
  // rather than axios's default `account_type[]=A`. The list endpoint reads a
  // repeated parameter as "any of these" (see src/mocks/query.ts), which is how
  // the Partners screen asks accounts for two account types at once.
  paramsSerializer: { indexes: null },

  // The session cookie rides along. Same-origin in dev through the Vite proxy,
  // so this is belt-and-braces rather than strictly required — but it is
  // required the moment the API is served from another origin.
  withCredentials: true,
})

/**
 * A session that has expired mid-visit sends the user back to sign in.
 *
 * Only for 401 (no valid session). A 403 is left alone deliberately: that means
 * signed in but not permitted — a pending-access user, or a non-admin reaching
 * Administration — and bouncing them to Microsoft would sign them in again,
 * land them back on the same 403, and loop.
 *
 * /auth/* is exempt because `GET /auth/me` answering 401 IS the normal
 * signed-out case that AuthProvider asks about on first load; redirecting on it
 * would mean nobody could ever see the sign-in screen.
 */
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status
    const url = String(error?.config?.url ?? '')
    if (status === 401 && !url.startsWith('/auth')) {
      window.location.assign('/api/auth/login')
    }
    return Promise.reject(error)
  }
)
