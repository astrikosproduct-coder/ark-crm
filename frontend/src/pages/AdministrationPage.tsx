import { useState } from 'react'
import { PlusIcon, DatabaseIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { PageLayout } from '@/components/layout/PageLayout'
import { UserDialog } from '@/components/admin/UserDialog'
import { DeletedFieldsTab } from '@/components/admin/metadata/DeletedFieldsTab'
import { FieldsTab } from '@/components/admin/metadata/FieldsTab'
import { LayoutTab } from '@/components/admin/metadata/LayoutTab'
import { ModulesTab } from '@/components/admin/metadata/ModulesTab'
import { PicklistsTab } from '@/components/admin/metadata/PicklistsTab'
import { PublishTab } from '@/components/admin/metadata/PublishTab'
import { StagesTab } from '@/components/admin/metadata/StagesTab'
import { DraftNotice } from '@/components/admin/metadata/shared'
import { useDraftStatus } from '@/lib/metadata'
import {
  errorMessage,
  useRoles,
  useSetUserActive,
  useUsers,
  type AdminUser,
} from '@/lib/admin'

/**
 * Administration — the first module backed by a real database, and since
 * Round 6 the place the field register itself is managed.
 *
 * Unlike every other screen, nothing here is stored in the browser. Reads and
 * writes go through the shared axios client to FastAPI and PostgreSQL, so this
 * data survives a refresh, a different browser and a cleared localStorage.
 *
 * The metadata tabs — Modules, Fields, Picklists, Stages, Deleted fields and
 * Publish — are Round 6. They edit a DRAFT in PostgreSQL and change nothing a
 * user sees until it is published, at which point the backend regenerates
 * spec/fields.json, spec/picklists.json and spec/stages.json, which is what the
 * rest of the CRM reads.
 *
 * All of it lives here rather than in a metadata area of its own: managing the
 * register is administration, and a second admin surface would be one more
 * place to look for the same kind of thing.
 */
export function AdministrationPage() {
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<AdminUser | undefined>(undefined)
  const [tab, setTab] = useState('users')

  // Only to show the pending-change count on the metadata tabs' banner; the
  // Publish tab fetches it again for the full review.
  const { data: draft } = useDraftStatus()
  const pending = draft?.changes.length ?? null

  const openAdd = () => {
    setEditing(undefined)
    setDialogOpen(true)
  }

  const openEdit = (user: AdminUser) => {
    setEditing(user)
    setDialogOpen(true)
  }

  /** Wraps a metadata tab in the "this is a draft" banner they all carry. */
  const metadataTab = (content: React.ReactNode) => (
    <>
      <DraftNotice pending={pending} />
      {content}
    </>
  )

  return (
    <>
      <PageLayout
        wide
        title="Administration"
        subtitle={
          <span className="inline-flex items-center gap-1.5">
            <DatabaseIcon className="size-3.5" />
            Live data — users, roles and the field register are stored in the database, not in
            this browser.
          </span>
        }
        activeTab={tab}
        onTabChange={setTab}
        actions={
          // Only on the Users tab: an Add user button while somebody is looking
          // at picklists would add a user to whatever they were reading.
          tab === 'users' ? (
            <Button onClick={openAdd}>
              <PlusIcon className="size-4" />
              Add user
            </Button>
          ) : undefined
        }
        tabs={[
          { key: 'users', label: 'Users', content: <UsersTab onEdit={openEdit} /> },
          { key: 'roles', label: 'Roles', content: <RolesTab /> },
          { key: 'modules', label: 'Modules', content: metadataTab(<ModulesTab />) },
          { key: 'fields', label: 'Fields', content: metadataTab(<FieldsTab />) },
          // Two views of one register, and both earn their place: Fields is
          // the table you read a property off, Layout is the form you see a
          // position in. Next to each other because the answer to "why is
          // this field there" is on one and the fix is on the other.
          { key: 'layout', label: 'Layout', content: metadataTab(<LayoutTab />) },
          { key: 'picklists', label: 'Picklists', content: metadataTab(<PicklistsTab />) },
          { key: 'stages', label: 'Stages', content: metadataTab(<StagesTab />) },
          {
            key: 'deleted',
            label: 'Deleted fields',
            content: metadataTab(<DeletedFieldsTab />),
          },
          { key: 'publish', label: 'Publish', content: <PublishTab /> },
        ]}
      />

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
          Administration needs the FastAPI backend on port 8000 and PostgreSQL on 5433.
        </p>
      </div>
    )
  }

  if (!users || users.length === 0) {
    return <p className="text-muted-foreground py-8 text-sm">No users yet.</p>
  }

  return (
    <div className="overflow-x-auto rounded-md border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-muted-foreground text-label">
          <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:text-left [&>th]:font-medium">
            <th className="w-28">User ID</th>
            {/* HR's number for this person, read from the directory on their
                first sign-in. Blank until then, and blank for good if the
                tenant does not populate employeeId — which is why it sits
                beside User ID rather than replacing it. */}
            <th className="w-28">Employee ID</th>
            <th>Name</th>
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
              <td className="text-muted-foreground font-mono text-xs">{user.user_id}</td>
              <td className="text-muted-foreground font-mono text-xs">
                {user.employee_id ?? <span className="opacity-50">—</span>}
              </td>
              <td className={user.active ? 'font-medium' : 'text-muted-foreground'}>
                {user.name}
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

function RolesTab() {
  const { data: roles, isLoading } = useRoles()

  if (isLoading) return <p className="text-muted-foreground py-8 text-sm">Loading roles…</p>

  return (
    <>
      <p className="text-muted-foreground mb-3 text-sm">
        System-defined and seeded from the field register. Creating roles and editing
        permissions is not built yet.
      </p>
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-muted-foreground text-label">
            <tr className="[&>th]:px-3 [&>th]:py-2 [&>th]:text-left [&>th]:font-medium">
              <th className="w-52">Role ID</th>
              <th className="w-52">Name</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {(roles ?? []).map((role) => (
              <tr key={role.role_id} className="border-t [&>td]:px-3 [&>td]:py-2">
                <td className="text-muted-foreground font-mono text-xs">{role.role_id}</td>
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
