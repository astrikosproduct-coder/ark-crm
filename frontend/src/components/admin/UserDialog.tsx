import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { MultiSelect } from '@/components/form/MultiSelect'
import { UserLookup } from '@/components/admin/UserLookup'
import {
  errorMessage,
  useCreateUser,
  useCreateUserFromDirectory,
  useNextUserId,
  useReplaceUserRoles,
  useRoles,
  useUpdateUser,
  useUsers,
  type AdminUser,
  type DirectoryPerson,
} from '@/lib/admin'
import type { PicklistOption } from '@/types/field'

/**
 * Add / edit a user and their roles.
 *
 * DELIBERATE EXCEPTION to CLAUDE.md rule 3 ("never hardcode a field"). Every
 * other form in the prototype renders from spec/fields.json through the form
 * engine. This one does not, because the register models Roles as a
 * `multiselect` against the administration__roles picklist, whereas the real
 * thing is a junction-table relationship (user_roles) saved through its own
 * endpoint. The form engine has no vocabulary for a relation, and bending it to
 * grow one for a single screen would distort the engine every other module
 * depends on. The engine is left untouched; this form owns its five fields.
 *
 * The register's USER & ROLE section is user_id, name, email, roles, active —
 * exactly the fields below, so the divergence is in the mechanism, not the
 * field list.
 */

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Present for edit, absent for add. */
  user?: AdminUser
}

interface FormState {
  user_id: string
  name: string
  email: string
  active: boolean
  role_ids: string[]
}

const EMPTY: FormState = { user_id: '', name: '', email: '', active: true, role_ids: [] }

export function UserDialog({ open, onOpenChange, user }: Props) {
  const isEdit = Boolean(user)

  const { data: roles = [] } = useRoles()
  // Only ask for a suggested id when adding, and only while the dialog is open.
  const { data: suggestedId } = useNextUserId(open && !isEdit)

  const createUser = useCreateUser()
  const createFromDirectory = useCreateUserFromDirectory()
  const updateUser = useUpdateUser()
  const replaceRoles = useReplaceUserRoles()

  const [form, setForm] = useState<FormState>(EMPTY)
  const [error, setError] = useState<string | null>(null)
  // Add mode starts on the lookup step: does this person already exist?
  const [step, setStep] = useState<'lookup' | 'details'>('lookup')
  // Set when the lookup matched someone — we are then editing their roles, not
  // creating a duplicate person.
  const [existing, setExisting] = useState<AdminUser | null>(null)
  // Set when the person was picked from the Astrikos directory. Their name and
  // email are Microsoft's and are shown read-only; the server reads them again.
  const [directoryPerson, setDirectoryPerson] = useState<DirectoryPerson | null>(null)

  useEffect(() => {
    if (!open) return
    setError(null)
    setDirectoryPerson(null)
    if (user) {
      setForm({
        user_id: user.user_id,
        name: user.name,
        email: user.email,
        active: user.active,
        role_ids: user.roles.map((r) => r.role_id),
      })
      setExisting(user)
      setStep('details')
    } else {
      setForm(EMPTY)
      setExisting(null)
      setStep('lookup')
    }
  }, [open, user])

  // Fill the suggested id once, and never over a value the admin has typed.
  useEffect(() => {
    if (!isEdit && suggestedId && !existing) {
      setForm((f) => (f.user_id === '' ? { ...f, user_id: suggestedId } : f))
    }
  }, [suggestedId, isEdit, existing])

  // Roles arrive from the database in the same shape a picklist option takes,
  // so MultiSelect is reused as-is rather than duplicated.
  const roleOptions: PicklistOption[] = roles.map((r) => ({
    key: r.role_id,
    label: r.name,
    sort: r.sort_order,
    active: r.active,
  }))
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  /** The lookup found them: their details come from the database, not retyped. */
  const pickExisting = (picked: AdminUser) => {
    setExisting(picked)
    setDirectoryPerson(null)
    setForm({
      user_id: picked.user_id,
      name: picked.name,
      email: picked.email,
      active: picked.active,
      role_ids: picked.roles.map((r) => r.role_id),
    })
    setStep('details')
  }

  const pickDirectory = (person: DirectoryPerson) => {
    setExisting(null)
    setDirectoryPerson(person)
    setForm({ ...EMPTY, name: person.name, email: person.email, user_id: suggestedId ?? '' })
    setStep('details')
  }

  const startNew = (typedName: string) => {
    setExisting(null)
    setDirectoryPerson(null)
    setForm({ ...EMPTY, name: typedName, user_id: suggestedId ?? '' })
    setStep('details')
  }

  const busy =
    createUser.isPending ||
    createFromDirectory.isPending ||
    updateUser.isPending ||
    replaceRoles.isPending

  const submit = async () => {
    setError(null)
    try {
      if (existing) {
        // Details and roles are two endpoints, because roles are a relation.
        await updateUser.mutateAsync({
          userId: existing.user_id,
          patch: { name: form.name.trim(), email: form.email.trim(), active: form.active },
        })
        await replaceRoles.mutateAsync({
          userId: existing.user_id,
          roleIds: form.role_ids,
        })
      } else if (directoryPerson) {
        await createFromDirectory.mutateAsync({
          entra_object_id: directoryPerson.entra_object_id,
          user_id: form.user_id.trim(),
          active: form.active,
          role_ids: form.role_ids,
        })
      } else {
        await createUser.mutateAsync({
          user_id: form.user_id.trim(),
          name: form.name.trim(),
          email: form.email.trim(),
          active: form.active,
          role_ids: form.role_ids,
        })
      }
      onOpenChange(false)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const canSubmit =
    form.user_id.trim() !== '' && form.name.trim() !== '' && form.email.trim() !== ''

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? `Edit ${user?.name}` : existing ? `Assign roles to ${existing.name}` : 'Add user'}
          </DialogTitle>
          <DialogDescription>
            {step === 'lookup'
              ? 'Check whether this person already exists before creating them.'
              : existing && !isEdit
                ? 'This person is already in the database. Their details are shown as stored — set their roles below.'
                : directoryPerson
                  ? "From the Astrikos directory. Name and email are Microsoft's — choose their roles, and they will have them from their first sign-in."
                  : 'Roles are stored as assignments, so a user can hold several.'}
          </DialogDescription>
        </DialogHeader>

        {step === 'lookup' ? (
          <AddLookupStep
            onPick={pickExisting}
            onPickDirectory={pickDirectory}
            onCreateNew={startNew}
          />
        ) : (
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="user_id">User ID</Label>
              <Input
                id="user_id"
                value={form.user_id}
                disabled={Boolean(existing)}
                onChange={(e) => set('user_id', e.target.value)}
                placeholder="USR-001"
              />
              {!existing && (
                <p className="text-muted-foreground text-xs">
                  Suggested from the highest existing id. You can change it.
                </p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={form.name}
                disabled={Boolean(directoryPerson)}
                onChange={(e) => set('name', e.target.value)}
                placeholder="Rahul Sharma"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={form.email}
                disabled={Boolean(directoryPerson)}
                onChange={(e) => set('email', e.target.value)}
                placeholder="rahul.sharma@astrikos.ai"
              />
            </div>

            {directoryPerson && (
              <p className="text-muted-foreground text-xs">
                {[
                  directoryPerson.job_title,
                  directoryPerson.department,
                  directoryPerson.employee_id && `Employee ID ${directoryPerson.employee_id}`,
                ]
                  .filter(Boolean)
                  .join(' · ') || 'No job title or department in the directory.'}
              </p>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="roles">Roles</Label>
              <MultiSelect
                id="roles"
                options={roleOptions}
                value={form.role_ids}
                onChange={(v) => set('role_ids', v)}
                placeholder="No roles assigned"
              />
            </div>

            <div className="flex items-center gap-2">
              <Checkbox
                id="active"
                checked={form.active}
                onCheckedChange={(v) => set('active', v === true)}
              />
              <Label htmlFor="active" className="font-normal">
                Active
              </Label>
            </div>

            {error && <p className="text-destructive text-sm">{error}</p>}
          </div>
        )}

        <DialogFooter>
          {step === 'details' && !isEdit && (
            <Button
              type="button"
              variant="ghost"
              onClick={() => setStep('lookup')}
              disabled={busy}
              className="mr-auto"
            >
              Back to search
            </Button>
          )}
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          {step === 'details' && (
            <Button onClick={submit} disabled={!canSubmit || busy}>
              {busy ? 'Saving…' : 'Save'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Kept separate so the users query only runs while the lookup step is shown. */
function AddLookupStep({
  onPick,
  onPickDirectory,
  onCreateNew,
}: {
  onPick: (user: AdminUser) => void
  onPickDirectory: (person: DirectoryPerson) => void
  onCreateNew: (typedName: string) => void
}) {
  const { data: users = [], isLoading } = useUsers()
  return (
    <div className="space-y-1.5 py-2">
      <Label>Find the person</Label>
      <UserLookup
        users={users}
        loading={isLoading}
        onPick={onPick}
        onPickDirectory={onPickDirectory}
        onCreateNew={onCreateNew}
      />
    </div>
  )
}
