import { useState } from 'react'
import { PlusIcon, ArrowUpIcon, ArrowDownIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { FieldDialog } from './FieldDialog'
import { ErrorBox, LoadingRow, Mono, Row, Table } from './shared'
import { errorMessage } from '@/lib/admin'
import {
  valueBehaviourOf,
  useCreateSection,
  useDeleteField,
  useRemovePlacement,
  useMetadataFields,
  useMetadataModules,
  useMetadataSections,
  useReorderFields,
  useSetFieldRequired,
  useUpdateSection,
  type MetadataField,
} from '@/lib/metadata'

/**
 * Modules, sections and fields on one screen.
 *
 * Kept together rather than split across three tabs because that is how the
 * register is actually read: nobody looks for "a section" — they look for the
 * Leads sheet and then for STAGE 4 within it. The module picker chooses the
 * sheet, the sections are its headings, and the fields sit under them in the
 * register's own order.
 */
export function FieldsTab() {
  const { data: modules = [], isLoading, isError, error } = useMetadataModules()
  const [moduleKey, setModuleKey] = useState<string>('leads')
  const [search, setSearch] = useState('')
  const [dialog, setDialog] = useState<{ open: boolean; field?: MetadataField; sectionId?: number }>(
    { open: false }
  )
  const [confirm, setConfirm] = useState<MetadataField | null>(null)

  const { data: sections = [] } = useMetadataSections(moduleKey)
  const { data: fields = [] } = useMetadataFields(moduleKey, 'active')

  const setRequired = useSetFieldRequired()
  const reorder = useReorderFields()

  if (isLoading) return <LoadingRow what="modules" />
  if (isError) return <ErrorBox error={error} />

  const term = search.trim().toLowerCase()
  const visible = term
    ? fields.filter(
        (f) =>
          f.api_name.toLowerCase().includes(term) || f.label.toLowerCase().includes(term)
      )
    : fields

  const ordered = [...fields].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))

  /** Move one field a place up or down within the module's own ordering. */
  const move = (field: MetadataField, delta: number) => {
    const index = ordered.findIndex((f) => f.id === field.id)
    const target = index + delta
    if (index < 0 || target < 0 || target >= ordered.length) return
    const next = [...ordered]
    ;[next[index], next[target]] = [next[target], next[index]]
    reorder.mutate(next.map((f) => f.id))
  }

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <select
          className="border-input bg-input-bg h-9 rounded-md border px-2 text-sm"
          value={moduleKey}
          onChange={(e) => setModuleKey(e.target.value)}
        >
          {modules.map((m) => (
            <option key={m.module_key} value={m.module_key}>
              {m.label} ({m.field_count})
            </option>
          ))}
        </select>

        <Input
          className="h-9 w-64"
          placeholder="Filter by name or label…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />

        <span className="text-muted-foreground text-xs">
          {visible.length} of {fields.length} field{fields.length === 1 ? '' : 's'}
        </span>

        <div className="ml-auto flex gap-2">
          <NewSectionButton moduleKey={moduleKey} />
          <Button size="sm" onClick={() => setDialog({ open: true })}>
            <PlusIcon className="size-4" />
            Add field
          </Button>
        </div>
      </div>

      {sections.length === 0 ? (
        <p className="text-muted-foreground py-8 text-sm">
          This module has no sections yet. Add one before adding fields.
        </p>
      ) : (
        sections.map((section) => {
          const rows = visible.filter((f) => f.section_id === section.id)
          if (term && rows.length === 0) return null

          return (
            <div key={section.id} className="mb-6">
              <SectionHeader
                sectionId={section.id}
                label={section.label}
                active={section.active}
                count={rows.length}
                onAddField={() => setDialog({ open: true, sectionId: section.id })}
              />

              {rows.length === 0 ? (
                <p className="text-muted-foreground py-3 text-sm">No fields in this section.</p>
              ) : (
                <Table
                  head={
                    <>
                      <th className="w-16">Order</th>
                      <th>Field</th>
                      <th className="w-28">Type</th>
                      <th className="w-32">Requirement</th>
                      <th className="w-24">Stage</th>
                      <th className="w-56" />
                    </>
                  }
                >
                  {rows.map((field) => {
                    const behaviour = valueBehaviourOf(field)
                    return (
                      <Row key={field.id}>
                        <td>
                          <div className="flex items-center gap-1">
                            <Mono>{field.sort_order}</Mono>
                            <button
                              className="hover:text-foreground text-muted-foreground"
                              title="Move up"
                              onClick={() => move(field, -1)}
                            >
                              <ArrowUpIcon className="size-3" />
                            </button>
                            <button
                              className="hover:text-foreground text-muted-foreground"
                              title="Move down"
                              onClick={() => move(field, 1)}
                            >
                              <ArrowDownIcon className="size-3" />
                            </button>
                          </div>
                        </td>
                        <td>
                          <div className="font-medium">{field.label}</div>
                          <Mono>{field.api_name}</Mono>
                          {/*
                            Where the value comes from, and what editing it
                            here does. Section 22: an administrator must be
                            able to see whether a field is owned, inherited or
                            carried without knowing anything about the schema.

                            The badge this replaced said "shows on
                            opportunities" — an apology for the fact that the
                            list was showing fields that render somewhere else.
                            The list is now this module's own fields, so there
                            is nothing left to apologise for.
                          */}
                          <div className="mt-0.5 flex flex-wrap gap-1">
                            <Badge
                              variant={behaviour.tone === 'owned' ? 'outline' : 'secondary'}
                              title={behaviour.detail}
                            >
                              {behaviour.label}
                            </Badge>
                            {field.module_count > 1 && (
                              <Badge
                                variant="secondary"
                                title={
                                  `This field is one definition shown on ${field.module_count} modules. ` +
                                  'Renaming it, or changing its type or picklist, changes all of them. ' +
                                  'Its section, order, stage and requirement are this module\u2019s alone.'
                                }
                              >
                                Used in {field.module_count} modules
                              </Badge>
                            )}
                            {!field.editable && (
                              <Badge
                                variant="secondary"
                                title="Read-only on this module. The value is resolved from the parent record."
                              >
                                read-only here
                              </Badge>
                            )}
                          </div>
                          {field.has_extension && (
                            <div className="mt-0.5">
                              <Badge
                                variant="outline"
                                title="This field has a computed expression, child-list shape or override in the hand-maintained spec/extensions.json"
                              >
                                sidecar
                              </Badge>
                            </div>
                          )}
                        </td>
                        <td>
                          <Mono>{field.field_type}</Mono>
                          {field.picklist_key && (
                            <div>
                              <Mono>{field.picklist_key}</Mono>
                            </div>
                          )}
                        </td>
                        <td>
                          <Button
                            size="sm"
                            variant={field.required ? 'default' : 'outline'}
                            disabled={setRequired.isPending}
                            title="Form validation only — never the database column's nullability"
                            onClick={() =>
                              setRequired.mutate({ placementId: field.placement_id, required: !field.required })
                            }
                          >
                            {field.required ? 'Required' : 'Not required'}
                          </Button>
                          {!['Mandatory', 'Optional'].includes(field.requirement) && (
                            <div className="mt-1">
                              <Mono>{field.requirement}</Mono>
                            </div>
                          )}
                        </td>
                        <td>
                          <Mono>
                            {field.capture_stage ?? '—'}
                            {field.mandatory_from !== null && ` · from ${field.mandatory_from}`}
                          </Mono>
                        </td>
                        <td className="text-right">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setDialog({ open: true, field })}
                          >
                            Edit
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-destructive"
                            onClick={() => setConfirm(field)}
                          >
                            Delete
                          </Button>
                        </td>
                      </Row>
                    )
                  })}
                </Table>
              )}
            </div>
          )
        })
      )}

      <FieldDialog
        open={dialog.open}
        onOpenChange={(open) => setDialog({ open })}
        moduleKey={moduleKey}
        field={dialog.field}
        sectionId={dialog.sectionId}
      />

      <DeleteFieldDialog field={confirm} onClose={() => setConfirm(null)} />
    </>
  )
}

/**
 * The delete confirmation, which is mostly an explanation.
 *
 * Deleting a field looks destructive and is not, and a dialog that just said
 * "Are you sure?" would leave somebody believing they had thrown away a
 * column of the CRM's data. It says exactly what survives, because that is the
 * fact that makes the decision safe to take.
 */
function DeleteFieldDialog({
  field,
  onClose,
}: {
  field: MetadataField | null
  onClose: () => void
}) {
  const removePlacement = useRemovePlacement()
  const deleteField = useDeleteField()
  const [error, setError] = useState<string | null>(null)

  const shared = (field?.module_count ?? 0) > 1

  const run = async (what: 'placement' | 'definition') => {
    if (!field) return
    setError(null)
    try {
      if (what === 'placement') await removePlacement.mutateAsync(field.placement_id)
      else await deleteField.mutateAsync(field.definition_id)
      onClose()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const busy = removePlacement.isPending || deleteField.isPending

  return (
    <Dialog open={Boolean(field)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete {field?.label}?</DialogTitle>
          <DialogDescription>
            {shared
              ? `This field is shown on ${field?.module_count} modules. There are two
                 different things you might mean, so both are offered separately.`
              : 'This is a logical delete, and it is reversible.'}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 text-sm">
          {/*
            Two actions, deliberately not one. "Remove from Opportunities" and
            "delete the field everywhere" are different decisions with different
            blast radii, and the pre-Round-7 model could only express the second
            — so an admin who wanted a field off one screen had no way to say
            so. Presenting them as one button with a checkbox would hide that.
          */}
          <div className="border-border rounded border p-3">
            <p className="mb-1 font-medium">
              Remove from {field?.module_key}
            </p>
            <p className="text-muted-foreground">
              The field stops appearing on {field?.module_key} at the next publish.
              {shared
                ? ` It stays on the other ${(field?.module_count ?? 1) - 1} module${
                    (field?.module_count ?? 1) - 1 === 1 ? '' : 's'
                  }, and the field itself is untouched.`
                : ' The field definition is kept, so it can be put back on this or any other module.'}
            </p>
          </div>

          <div className="border-border rounded border p-3">
            <p className="mb-1 font-medium">Delete the field everywhere</p>
            <p className="text-muted-foreground">
              {shared
                ? `Removes it from all ${field?.module_count} modules at once.`
                : 'Deletes the field itself.'}{' '}
              Restoring it later brings back exactly the modules this delete took
              it off — a module you had removed it from separately stays removed.
            </p>
          </div>

          <div>
            <p className="mb-1 font-medium">Neither of these touches your data</p>
            <ul className="text-muted-foreground list-disc space-y-0.5 pl-5">
              <li>
                The database column is <strong>not</strong> dropped, and no
                stored value is deleted.
              </li>
              <li>
                The configuration is kept, so a restore brings the field and its
                data back exactly as they were.
              </li>
            </ul>
          </div>
          <p className="text-muted-foreground text-xs">
            Deleted fields are listed under the Deleted fields tab, where they can be
            restored.
          </p>
          {error && <p className="text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="outline" disabled={busy} onClick={() => run('placement')}>
            {removePlacement.isPending
              ? 'Removing…'
              : `Remove from ${field?.module_key}`}
          </Button>
          <Button
            variant="destructive"
            disabled={busy}
            onClick={() => run('definition')}
          >
            {deleteField.isPending ? 'Deleting…' : 'Delete everywhere'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}


/**
 * Rename a section, or switch it off.
 *
 * A section is renamed rather than recreated because field placements point at
 * its id — the label is not the identity. Deactivating is the only "delete" on
 * offer: a section with fields in it must not be able to take them off every
 * screen without those fields being dealt with individually.
 */
function SectionHeader({
  sectionId,
  label,
  active,
  count,
  onAddField,
}: {
  sectionId: number
  label: string
  active: boolean
  count: number
  onAddField: () => void
}) {
  const updateSection = useUpdateSection()
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(label)
  const [error, setError] = useState<string | null>(null)

  const save = async () => {
    setError(null)
    try {
      await updateSection.mutateAsync({ sectionId, patch: { label: value.trim() } })
      setEditing(false)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <div className="border-border mb-2 flex items-center gap-2 border-b pb-1">
      {editing ? (
        <>
          <Input
            className="h-7 max-w-sm"
            value={value}
            autoFocus
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void save()
              if (e.key === 'Escape') {
                setValue(label)
                setEditing(false)
              }
            }}
          />
          <Button size="sm" disabled={updateSection.isPending} onClick={() => void save()}>
            Save
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setValue(label)
              setEditing(false)
            }}
          >
            Cancel
          </Button>
        </>
      ) : (
        <>
          <button
            className="hover:text-foreground text-left text-sm font-semibold"
            title="Rename this section"
            onClick={() => setEditing(true)}
          >
            {label}
          </button>
          <span className="text-muted-foreground text-xs">
            {count} field{count === 1 ? '' : 's'}
          </span>
          {!active && <Badge variant="secondary">inactive</Badge>}
          <Button size="sm" variant="ghost" className="ml-auto" onClick={onAddField}>
            <PlusIcon className="size-4" />
            Add field here
          </Button>
        </>
      )}
      {error && <span className="text-destructive text-xs">{error}</span>}
    </div>
  )
}


/**
 * Add a section to the module currently selected.
 *
 * Sections are per module and their labels are unique within one, which is the
 * invariant the qref (module.section.api_name) depends on — the API refuses a
 * duplicate rather than creating a second section nothing could tell apart.
 */
function NewSectionButton({ moduleKey }: { moduleKey: string }) {
  const createSection = useCreateSection()
  const [open, setOpen] = useState(false)
  const [label, setLabel] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setError(null)
    try {
      await createSection.mutateAsync({ module_key: moduleKey, label: label.trim() })
      setLabel('')
      setOpen(false)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <PlusIcon className="size-4" />
        Add section
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add section to {moduleKey}</DialogTitle>
            <DialogDescription>
              Sections group a module's fields on the form. The name must be unique
              within the module.
            </DialogDescription>
          </DialogHeader>

          <Input
            value={label}
            autoFocus
            placeholder="STAGE 4 — RFP / RFI"
            onChange={(e) => setLabel(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && label.trim()) void submit()
            }}
          />
          {error && <p className="text-destructive text-sm">{error}</p>}

          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={!label.trim() || createSection.isPending}
              onClick={() => void submit()}
            >
              {createSection.isPending ? 'Adding…' : 'Add section'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
