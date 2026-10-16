import { useState } from 'react'
import { PlusIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { UserDialog } from '@/components/admin/UserDialog'
import {
  errorMessage,
  useRoles,
  useSetUserActive,
  useUsers,
  type AdminUser,
} from '@/lib/admin'

/**
 * Setup → Users and Control → Users.
 *
 * Moved out of the old Administration page unchanged. The Add user button used
 * to sit in the page header and was shown only while the Users tab was open;
 * each Setup item is its own page now, so it sits above the table — where Zoho
 * puts "New User".
 */
export function UsersPanel() {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<AdminUser | undefined>(undefined)

  const openAdd = () => {
    setEditing(undefined)
    setDialogOpen(true)
  }

  const openEdit = (user: AdminUser) => {
    setEditing(user)
    setDialogOpen(true)
  }

  return (
    <>
      <div className="mb-3 flex justify-end">
        <Button onClick={openAdd}>
          <PlusIcon className="size-4" />
          Add user
        </Button>
      </div>
      <UsersTab onEdit={openEdit} />
      <UserDialog open={dialogOpen} onOpenChange={setDialogOpen} user={editing} />
    </>
  )
}

function UsersTab({ onEdit }: { onEdit: (user: AdminUser) => void }) {
  const { data: users, isLoading, isError, error } = useUsers()
  const setActive = useSetUserActive()

  if (isLoading) {
    return <p className="text-muted-foreground py-8 text-sm">Loading users…</p>
  }

  if (isError) {
    return (
      <div className="border-destructive/40 bg-destructive/5 rounded-md border p-4">
        <p className="text-destructive text-sm font-medium">Could not reach the API</p>
        <p className="text-muted-foreground mt-1 text-sm">{errorMessage(error)}</p>
        <p className="text-muted-foreground mt-2 text-xs">
          Setup needs the FastAPI backend on port 8000 and PostgreSQL on 5433.
        </p>
      </div>
    )
  }

  if (!users || users.length === 0) {
    return <p className="text-muted-foreground py-8 text-sm">No users yet.</p>
  }

  return (
    <div className="bg-card overflow-x-auto rounded-lg shadow-sm">
      <table className="w-full text-sm">
        <thead className="text-muted-foreground text-label [&>tr>th]:border-border [&>tr>th]:border-b">
          <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:text-left [&>th]:font-medium">
            {/* No User ID column: ARK shows no record numbers (14 Oct 2026).
                Employee ID is HR's number for the person, not ARK's. */}
            <th>Name</th>
            <th className="w-28">Employee ID</th>
            <th>Email</th>
            <th>Roles</th>
            <th className="w-24">Status</th>
            <th className="w-44" />
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr
              key={user.user_id}
              className="border-t [&>td]:px-3 [&>td]:py-2 [&>td]:align-top"
            >
              <td className={user.active ? 'font-medium' : 'text-muted-foreground'}>
                {user.name}
              </td>
              <td className="text-muted-foreground font-mono text-xs">
                {user.employee_id ?? <span className="opacity-50">—</span>}
              </td>
              <td className="text-muted-foreground">{user.email}</td>
              <td>
                {user.roles.length === 0 ? (
                  <span className="text-muted-foreground text-xs">No roles</span>
                ) : (
                  <span>{user.roles.map((role) => role.name).join(', ')}</span>
                )}
              </td>
              <td>
                <span className={user.active ? undefined : 'text-muted-foreground'}>
                  {user.active ? 'Active' : 'Inactive'}
                </span>
              </td>
              <td className="text-right">
                <Button size="sm" variant="ghost" onClick={() => onEdit(user)}>
                  Edit
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={setActive.isPending}
                  onClick={() =>
                    setActive.mutate({ userId: user.user_id, active: !user.active })
                  }
                >
                  {user.active ? 'Deactivate' : 'Activate'}
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Setup → Users and Control → Roles. Moved out of Administration unchanged. */
export function RolesPanel() {
  const { data: roles, isLoading } = useRoles()

  if (isLoading) return <p className="text-muted-foreground py-8 text-sm">Loading roles…</p>

  return (
    <>
      <p className="text-muted-foreground mb-3 text-sm">
        System-defined and seeded from the field register. Creating roles and editing
        permissions is not built yet.
      </p>
      <div className="bg-card overflow-x-auto rounded-lg shadow-sm">
        <table className="w-full text-sm">
          <thead className="text-muted-foreground text-label [&>tr>th]:border-border [&>tr>th]:border-b">
            <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:text-left [&>th]:font-medium">
              <th className="w-52">Name</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {(roles ?? []).map((role) => (
              <tr key={role.role_id} className="border-t [&>td]:px-3 [&>td]:py-2">
                <td className="font-medium">{role.name}</td>
                <td className="text-muted-foreground">{role.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
