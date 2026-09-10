/**
 * Who is signed in, readable from anywhere.
 *
 * WHY A MODULE-LEVEL GETTER AND NOT ONLY A HOOK
 * ---------------------------------------------
 * The identity this replaces was a hardcoded `CURRENT_USER_ID` constant, read
 * from 39 places — event handlers in dialogs, page callbacks, and plain
 * non-React helpers like lib/recordLifecycle.ts. A hook cannot be called from
 * the latter, and turning every one of those call sites into a hook would be a
 * large, risky refactor of code that is otherwise working.
 *
 * So AuthProvider pushes the signed-in user in here once, and call sites read
 * `currentUserId()` — a one-word change from the constant they used before.
 * Components that need the name, roles or pending state should still prefer
 * the `useAuth()` hook, which re-renders properly when identity changes.
 */

export interface CurrentUser {
  user_id: string
  name: string
  email: string
  /** From the Microsoft directory, filled on sign-in — null if the tenant does
   *  not set employeeId. Always present in the /auth/me payload. */
  employee_id: string | null
  roles: string[]
  is_admin: boolean
  pending: boolean
}

/**
 * The two letters shown in the avatar: first name, last name.
 *
 * Middle names are skipped — "Kishan M Pawar" is KP, not KM — because the point
 * is to be recognisable at 28px, and the surname is what distinguishes two
 * people who share a first name. A single-word name gives a single letter
 * rather than an invented second one.
 */
export function initialsOf(name: string): string {
  const parts = name
    .trim()
    .split(/\s+/)
    .filter((part) => /\p{L}/u.test(part))

  if (parts.length === 0) return '?'
  const first = parts[0]
  const last = parts.length > 1 ? parts[parts.length - 1] : ''
  return (first[0] + (last[0] ?? '')).toUpperCase()
}

let current: CurrentUser | null = null

export function setCurrentUser(user: CurrentUser | null): void {
  current = user
}

export function getCurrentUser(): CurrentUser | null {
  return current
}

/**
 * The signed-in user's id, for stamping created_by / modified_by / actor.
 *
 * Throws rather than returning a placeholder when nobody is signed in: writing
 * a record with a guessed or empty owner is precisely the bug this replaced —
 * an audit trail that names the wrong person is worse than one that fails
 * loudly. Every caller runs inside an authenticated screen, so this cannot
 * happen without a bug elsewhere.
 */
export function currentUserId(): string {
  if (!current) {
    throw new Error('No signed-in user — an authenticated screen wrote a record without a session.')
  }
  return current.user_id
}
