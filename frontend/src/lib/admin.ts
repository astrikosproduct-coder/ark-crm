import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api'
import { refusalOf, type RefusalOptions } from '@/lib/errors'
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

/** A person in the Astrikos Microsoft directory — see backend/app/graph_directory.py. */
export interface DirectoryPerson {
  entra_object_id: string
  name: string
  email: string
  employee_id: string | null
  job_title: string | null
  department: string | null
  /** Set when this person is already in ARK CRM. */
  user_id: string | null
}

export interface UserFromDirectoryInput {
  entra_object_id: string
  user_id?: string
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
  directory: (q: string) => ['admin', 'directory', q] as const,
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

/**
 * Search the Astrikos directory. Two characters minimum, as the server
 * requires. Not retried: the usual failure is a missing Graph permission,
 * and asking again three times does not grant it.
 */
export function useDirectorySearch(q: string) {
  const text = q.trim()
  return useQuery({
    queryKey: adminKeys.directory(text),
    queryFn: async () =>
      (await api.get<DirectoryPerson[]>(`${BASE}/directory/people`, { params: { q: text } })).data,
    enabled: text.length >= 2,
    retry: false,
    staleTime: 60_000,
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

/** Name, email and employee id are read from the directory by the server. */
export function useCreateUserFromDirectory() {
  const invalidate = useInvalidateUsers()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (input: UserFromDirectoryInput) =>
      (await api.post<AdminUser>(`${BASE}/users/from-directory`, input)).data,
    onSuccess: () => {
      invalidate()
      // Search results carry "already in ARK CRM" — stale the moment someone is added.
      void queryClient.invalidateQueries({ queryKey: ['admin', 'directory'] })
    },
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

/**
 * The server's refusal as ONE line of text, for places with room for a single
 * string (a toast-like status, an input's error slot). Anywhere with room for
 * more, render <ErrorNotice> instead — it keeps the bullets separate rather
 * than running them together.
 */
export function errorMessage(error: unknown, options: RefusalOptions = {}): string {
  const refusal = refusalOf(error, options)
  return [refusal.message, ...refusal.details].join(' ')
}
