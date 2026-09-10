import { useState, type ReactNode } from 'react'
import { LogOutIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { useAuth } from '@/lib/auth'
import { initialsOf } from '@/lib/currentUser'
import { labelForValue } from '@/lib/spec'

/** The picklist the roles are seeded from — CLAUDE.md rule 4, never a literal. */
const ROLE_PICKLIST = 'administration__roles'

/**
 * The signed-in user in the top bar: an avatar, and everything else behind it.
 *
 * The bar carries the initials alone. Who someone is — their employee id, the
 * roles that decide what they can reach, the way out — lives in the drawer,
 * where there is room to state it plainly rather than abbreviate it into a
 * strip of chrome.
 */
export function UserMenu() {
  const [open, setOpen] = useState(false)
  const { user, signOut } = useAuth()

  if (!user) return null

  const initials = initialsOf(user.name)

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={`Account — ${user.name}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        className="bg-avatar-accent focus-visible:ring-ring/50 ml-1.5 flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white transition-opacity hover:opacity-90 focus-visible:ring-[3px] focus-visible:outline-none"
      >
        {initials}
      </button>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent aria-describedby={undefined}>
          <SheetHeader className="flex-row items-center gap-3">
            <span className="bg-avatar-accent flex size-11 shrink-0 items-center justify-center rounded-full text-sm font-bold text-white">
              {initials}
            </span>
            <span className="min-w-0">
              <SheetTitle className="truncate">{user.name}</SheetTitle>
              <span className="text-muted-foreground text-meta mt-1 block truncate">
                {user.email}
              </span>
            </span>
          </SheetHeader>

          <dl className="flex flex-col gap-4 border-t pt-5">
            {/* The ARK user id, not the directory's employee_id: this is the
                value that appears as an owner on every record, so it is the one
                worth being able to read off your own profile. */}
            <Detail label="User ID">
              <span className="font-mono">{user.user_id}</span>
            </Detail>

            <Detail label="Name">{user.name}</Detail>

            <Detail label="Email">
              <span className="break-all">{user.email}</span>
            </Detail>

            <Detail label={user.roles.length === 1 ? 'Role assigned' : 'Roles assigned'}>
              {user.roles.length === 0 ? (
                <span className="text-muted-foreground">No roles assigned</span>
              ) : (
                <span>{user.roles.map((role) => labelForValue(ROLE_PICKLIST, role)).join(', ')}</span>
              )}
            </Detail>
          </dl>

          <div className="mt-auto border-t pt-5">
            <Button
              type="button"
              variant="outline"
              className="w-full"
              onClick={() => {
                setOpen(false)
                void signOut()
              }}
            >
              <LogOutIcon className="size-4" />
              Sign out
            </Button>
          </div>
        </SheetContent>
      </Sheet>
    </>
  )
}

/** Label above value, the way the record screens read. */
function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-muted-foreground text-label">{label}</dt>
      <dd className="text-foreground mt-0.5 text-sm">{children}</dd>
    </div>
  )
}
