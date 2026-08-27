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
})
