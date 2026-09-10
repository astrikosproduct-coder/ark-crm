import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { invalidateUserDirectory } from '@/mocks/userDirectory'

/**
 * Administration data layer.
 *
 * The only module backed by a real database. It still goes through the shared
 * axios client in src/lib/api.ts — CLAUDE.md rule 2 — so React sees no
 * difference between a mocked module and this one. What differs is downstream:
 * MSW passes /api/admin/* through (src/mocks/handlers.ts) and Vite proxies it
 * to FastAPI, which reads PostgreSQL.
 */

export interface Role {
  role_id: string
  name: string
  description: string | null
  sort_order: number
  active: boolean
}

export interface AdminUser {
  user_id: string
  name: string
  email: string
  active: boolean
  created_at: string
  updated_at: string
  roles: Role[]

  /** From the Microsoft directory, filled on sign-in. Null until they have
   *  signed in once, and null for good if the tenant never sets employeeId. */
  employee_id: string | null
  last_login_at: string | null
}

export interface UserCreateInput {
  user_id: string
  name: string
  email: string
  active?: boolean
  role_ids: string[]
}

export interface UserUpdateInput {
  name?: string
  email?: string
  active?: boolean
}

const BASE = '/admin'

export const adminKeys = {
  users: ['admin', 'users'] as const,
  roles: ['admin', 'roles'] as const,
  nextId: ['admin', 'next-user-id'] as const,
}

export function useRoles() {
  return useQuery({
    queryKey: adminKeys.roles,
    queryFn: async () => (await api.get<Role[]>(`${BASE}/roles`)).data,
    // System-defined and seeded — they do not change while the app is open.
    staleTime: Infinity,
  })
}

export function useUsers() {
  return useQuery({
    queryKey: adminKeys.users,
    queryFn: async () => (await api.get<AdminUser[]>(`${BASE}/users`)).data,
  })
}

/** The suggested next USR-00N. A suggestion only — the admin may overwrite it. */
export function useNextUserId(enabled: boolean) {
  return useQuery({
    queryKey: adminKeys.nextId,
    queryFn: async () =>
      (await api.get<{ user_id: string }>(`${BASE}/users/next-id`)).data.user_id,
    enabled,
    staleTime: 0,
  })
}

function useInvalidateUsers() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: adminKeys.users })
    void queryClient.invalidateQueries({ queryKey: adminKeys.nextId })

    // The rest of the application reads users through /api/users under the
    // 'collection' key — every owner lookup, and the Leads owner filter.
    void queryClient.invalidateQueries({ queryKey: ['collection', 'users'] })

    // And MSW caches the same directory to join owner names onto list rows, so
    // a rename would otherwise keep showing the old name on a lead.
    invalidateUserDirectory()
  }
}

export function useCreateUser() {
  const invalidate = useInvalidateUsers()
  return useMutation({
    mutationFn: async (input: UserCreateInput) =>
      (await api.post<AdminUser>(`${BASE}/users`, input)).data,
    onSuccess: invalidate,
  })
}

export function useUpdateUser() {
  const invalidate = useInvalidateUsers()
  return useMutation({
    mutationFn: async ({ userId, patch }: { userId: string; patch: UserUpdateInput }) =>
      (await api.patch<AdminUser>(`${BASE}/users/${userId}`, patch)).data,
    onSuccess: invalidate,
  })
}

export function useSetUserActive() {
  const invalidate = useInvalidateUsers()
  return useMutation({
    mutationFn: async ({ userId, active }: { userId: string; active: boolean }) =>
      (await api.patch<AdminUser>(`${BASE}/users/${userId}/active`, { active })).data,
    onSuccess: invalidate,
  })
}

/** Replaces the whole role set. An empty array removes every role. */
export function useReplaceUserRoles() {
  const invalidate = useInvalidateUsers()
  return useMutation({
    mutationFn: async ({ userId, roleIds }: { userId: string; roleIds: string[] }) =>
      (await api.put<Role[]>(`${BASE}/users/${userId}/roles`, { role_ids: roleIds })).data,
    onSuccess: invalidate,
  })
}

/** Pulls the server's message out of an axios error, falling back to its own. */
export function errorMessage(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data
    ?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // FastAPI validation errors arrive as a list of {loc, msg}.
    const first = detail[0] as { loc?: unknown[]; msg?: string } | undefined
    if (first?.msg) {
      const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : undefined
      return field ? `${String(field)}: ${first.msg}` : first.msg
    }
  }
  return error instanceof Error ? error.message : 'Something went wrong'
}
