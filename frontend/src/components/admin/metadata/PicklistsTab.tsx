import { useState } from 'react'
import { PlusIcon, ArrowUpIcon, ArrowDownIcon, ChevronRightIcon, ChevronDownIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
import { ErrorBox, LoadingRow, Mono, Row, StatusBadge, Table } from './shared'
import { errorMessage } from '@/lib/admin'
import {
  useCreatePicklist,
  useCreatePicklistValue,
  useMetadataPicklists,
  useReorderPicklistValues,
  useUpdatePicklist,
  useUpdatePicklistValue,
  type MetadataPicklist,
} from '@/lib/metadata'

/**
 * Every dropdown in the CRM, and the values behind it.
 *
 * WHY NOTHING HERE CAN BE RENAMED OR DELETED
 * -------------------------------------------
 * A picklist value's KEY is what records store — INFRASTRUCTURE, not
 * "Infrastructure" — and what the register's own conditions and lookup filters
 * compare against. Renaming it would leave every record already holding it
 * pointing at an option that no longer exists, and the dropdown would render
 * blank on records that were filled in correctly.
 *
 * So: labels are editable, keys are not, and a value that should no longer be
 * chosen is DEACTIVATED. Existing records keep resolving it; nobody can pick it
 * again. Same rule one level up for the picklist itself.
 */
export function PicklistsTab() {
  const { data: picklists = [], isLoading, isError, error } = useMetadataPicklists()
  const [expanded, setExpanded] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [adding, setAdding] = useState(false)

  if (isLoading) return <LoadingRow what="picklists" />
  if (isError) return <ErrorBox error={error} />

  const term = search.trim().toLowerCase()
  const visible = term
    ? picklists.filter((p) => p.picklist_key.toLowerCase().includes(term))
    : picklists

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Input
          className="h-9 w-64"
          placeholder="Filter picklists…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <span className="text-muted-foreground text-xs">
          {visible.length} of {picklists.length}
        </span>
        <Button size="sm" className="ml-auto" onClick={() => setAdding(true)}>
          <PlusIcon className="size-4" />
          Add picklist
        </Button>
      </div>

      <Table
        head={
          <>
            <th className="w-8" />
            <th>Picklist</th>
            <th className="w-24">Values</th>
            <th className="w-24">Used by</th>
            <th className="w-24">Status</th>
            <th className="w-32" />
          </>
        }
      >
        {visible.map((picklist) => (
          <PicklistRows
            key={picklist.picklist_key}
            picklist={picklist}
            open={expanded === picklist.picklist_key}
            onToggle={() =>
              setExpanded(expanded === picklist.picklist_key ? null : picklist.picklist_key)
            }
          />
        ))}
      </Table>

      <AddPicklistDialog open={adding} onOpenChange={setAdding} />
    </>
  )
}

function PicklistRows({
  picklist,
  open,
  onToggle,
}: {
  picklist: MetadataPicklist
  open: boolean
  onToggle: () => void
}) {
  const updatePicklist = useUpdatePicklist()
  const updateValue = useUpdatePicklistValue()
  const reorder = useReorderPicklistValues()
  const [addingValue, setAddingValue] = useState(false)

  const move = (valueId: number, delta: number) => {
    const ids = picklist.values.map((v) => v.id)
    const index = ids.indexOf(valueId)
    const target = index + delta
    if (index < 0 || target < 0 || target >= ids.length) return
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    reorder.mutate(ids)
  }

  return (
    <>
      <Row muted={!picklist.active}>
        <td>
          <button onClick={onToggle} className="text-muted-foreground hover:text-foreground">
            {open ? <ChevronDownIcon className="size-4" /> : <ChevronRightIcon className="size-4" />}
          </button>
        </td>
        <td>
          <div className="flex items-center gap-2 font-medium">
            {picklist.label ?? picklist.picklist_key}
            <Badge
              variant={picklist.is_global ? 'secondary' : 'outline'}
              title={
                picklist.is_global
                  ? 'Global — shared by fields on several modules. A change here changes all of them.'
                  : 'Local — serves one field.'
              }
            >
              {picklist.is_global ? 'Global' : 'Local'}
            </Badge>
          </div>
          <Mono>{picklist.picklist_key}</Mono>
        </td>
        <td>{picklist.values.length}</td>
        <td>
          {picklist.field_count === 0 ? (
            <span className="text-muted-foreground text-xs">no fields</span>
          ) : (
            `${picklist.field_count} field${picklist.field_count === 1 ? '' : 's'}`
          )}
        </td>
        <td>
          <StatusBadge active={picklist.active} />
        </td>
        <td className="text-right">
          <Button
            size="sm"
            variant="ghost"
            title={
              picklist.active && picklist.field_count > 0
                ? 'Fields still use this — publish will refuse until they are repointed'
                : undefined
            }
            onClick={() =>
              updatePicklist.mutate({
                picklistKey: picklist.picklist_key,
                patch: { active: !picklist.active },
              })
            }
          >
            {picklist.active ? 'Deactivate' : 'Activate'}
          </Button>
        </td>
      </Row>

      {open && (
        <tr className="bg-muted/20 border-t">
          <td />
          <td colSpan={5} className="px-3 py-3">
            <div className="mb-2 flex items-center gap-2">
              <span className="text-xs font-medium">Values</span>
              <Button size="sm" variant="outline" onClick={() => setAddingValue(true)}>
                <PlusIcon className="size-3" />
                Add value
              </Button>
              <span className="text-muted-foreground text-xs">
                Keys are fixed — records already store them. Edit the label, or deactivate.
              </span>
            </div>

            <table className="w-full text-sm">
              <tbody>
                {picklist.values.map((value) => (
                  <tr key={value.id} className="[&>td]:py-1 [&>td]:pr-3">
                    <td className="w-16">
                      <div className="flex items-center gap-1">
                        <Mono>{value.sort_order}</Mono>
                        <button
                          className="text-muted-foreground hover:text-foreground"
                          onClick={() => move(value.id, -1)}
                        >
                          <ArrowUpIcon className="size-3" />
                        </button>
                        <button
                          className="text-muted-foreground hover:text-foreground"
                          onClick={() => move(value.id, 1)}
                        >
                          <ArrowDownIcon className="size-3" />
                        </button>
                      </div>
                    </td>
                    <td className="w-64">
                      <Mono>{value.key}</Mono>
                    </td>
                    <td>
                      <InlineLabel
                        value={value.label}
                        onSave={(label) =>
                          updateValue.mutate({ valueId: value.id, patch: { label } })
                        }
                      />
                    </td>
                    <td className="w-24">
                      {value.active ? null : <Badge variant="outline">Inactive</Badge>}
                      {value.is_system && (
                        <Badge
                          variant="secondary"
                          title="The CRM's own rules read this choice. It can be renamed, not retired."
                        >
                          Used by the CRM
                        </Badge>
                      )}
                    </td>
                    <td className="w-28 text-right">
                      {!(value.is_system && value.active) && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() =>
                            updateValue.mutate({
                              valueId: value.id,
                              patch: { active: !value.active },
                            })
                          }
                        >
                          {value.active ? 'Deactivate' : 'Activate'}
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <AddValueDialog
              picklistKey={picklist.picklist_key}
              open={addingValue}
              onOpenChange={setAddingValue}
            />
          </td>
        </tr>
      )}
    </>
  )
}

function InlineLabel({ value, onSave }: { value: string; onSave: (label: string) => void }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)

  if (!editing) {
    return (
      <button
        className="hover:bg-muted rounded px-1 text-left"
        onClick={() => {
          setDraft(value)
          setEditing(true)
        }}
      >
        {value}
      </button>
    )
  }

  const save = () => {
    if (draft.trim() && draft !== value) onSave(draft.trim())
    setEditing(false)
  }

  return (
    <Input
      className="h-7"
      autoFocus
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={save}
      onKeyDown={(e) => {
        if (e.key === 'Enter') save()
        if (e.key === 'Escape') setEditing(false)
      }}
    />
  )
}

function AddValueDialog({
  picklistKey,
  open,
  onOpenChange,
}: {
  picklistKey: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const createValue = useCreatePicklistValue()
  const [key, setKey] = useState('')
  const [label, setLabel] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setError(null)
    try {
      await createValue.mutateAsync({
        picklist_key: picklistKey,
        key: key.trim(),
        label: label.trim(),
      })
      setKey('')
      setLabel('')
      onOpenChange(false)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add value to {picklistKey}</DialogTitle>
          <DialogDescription>
            The key is what records store and it cannot be changed afterwards. The register's
            convention is upper snake case — PARTNER_SOURCED.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="value_key">Key</Label>
            <Input
              id="value_key"
              value={key}
              placeholder="PARTNER_SOURCED"
              onChange={(e) => setKey(e.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="value_label">Label</Label>
            <Input
              id="value_label"
              value={label}
              placeholder="Partner-sourced"
              onChange={(e) => setLabel(e.target.value)}
            />
          </div>
          {error && <p className="text-destructive text-sm">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!key.trim() || !label.trim() || createValue.isPending} onClick={submit}>
            Add value
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AddPicklistDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const createPicklist = useCreatePicklist()
  const [key, setKey] = useState('')
  const [label, setLabel] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setError(null)
    try {
      await createPicklist.mutateAsync({ picklist_key: key.trim(), label: label.trim() })
      setKey('')
      setLabel('')
      onOpenChange(false)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add picklist</DialogTitle>
          <DialogDescription>
            The register names picklists <code>module__field</code> — leads__deal_source. A
            picklist with no values behind it renders as free text.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="picklist_key">Key</Label>
            <Input
              id="picklist_key"
              value={key}
              placeholder="leads__deal_source"
              onChange={(e) => setKey(e.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="picklist_label">Label</Label>
            <Input
              id="picklist_label"
              value={label}
              placeholder="Leads · Deal Source"
              onChange={(e) => setLabel(e.target.value)}
            />
          </div>
          {error && <p className="text-destructive text-sm">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!/^[a-z][a-z0-9_]*$/.test(key.trim()) || createPicklist.isPending}
            onClick={submit}
          >
            Add picklist
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
