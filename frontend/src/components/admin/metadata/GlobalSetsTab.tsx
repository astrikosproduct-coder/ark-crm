import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronDownIcon, ChevronRightIcon, PlusIcon } from 'lucide-react'

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
import { Textarea } from '@/components/ui/textarea'
import { ChoicesEditor } from './ChoicesEditor'
import { ErrorBox, LoadingRow, Mono, Row, StatusBadge, Table } from './shared'
import { errorMessage } from '@/lib/admin'
import {
  choiceLines,
  useCreatePicklist,
  useMetadataPicklists,
  useUpdatePicklist,
  type MetadataPicklist,
} from '@/lib/metadata'

/**
 * Global Sets — the lists shared by several fields. Zoho's own name, and its
 * place: a tab beside Modules in Modules and Fields (Setup rebuild, 25 Sep
 * 2026, which removed the Picklists screen this file used to be).
 *
 * A list serving ONE field is not here: Zoho keeps it inside the field, and so
 * does ARK — the field dialog's Choices. A change to a set changes every field
 * in its "Used in", which is why that list is one click away on every row.
 *
 * A set used by more than one field stays global (PICKLIST_SHARED), and a
 * local list is never turned into one here — Zoho offers neither.
 */
export function GlobalSetsTab({ moduleHref }: { moduleHref: (moduleKey: string) => string }) {
  const { data: picklists = [], isLoading, isError, error } = useMetadataPicklists()
  const [expanded, setExpanded] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [adding, setAdding] = useState(false)

  if (isLoading) return <LoadingRow what="global sets" />
  if (isError) return <ErrorBox error={error} />

  const sets = picklists.filter((p) => p.is_global)
  const term = search.trim().toLowerCase()
  const visible = term
    ? sets.filter(
        (p) =>
          (p.label ?? '').toLowerCase().includes(term) ||
          p.picklist_key.toLowerCase().includes(term)
      )
    : sets

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Input
          className="h-9 w-64"
          placeholder="Filter global sets…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <span className="text-muted-foreground text-xs">
          {visible.length} of {sets.length}
        </span>
        <Button size="sm" className="ml-auto" onClick={() => setAdding(true)}>
          <PlusIcon className="size-4" />
          New global set
        </Button>
      </div>

      <Table
        head={
          <>
            <th className="w-8" />
            <th>Global set</th>
            <th className="w-24">Choices</th>
            <th className="w-28">Used in</th>
            <th className="w-24">Status</th>
            <th className="w-32" />
          </>
        }
      >
        {visible.map((set) => (
          <SetRows
            key={set.picklist_key}
            set={set}
            open={expanded === set.picklist_key}
            onToggle={() => setExpanded(expanded === set.picklist_key ? null : set.picklist_key)}
            moduleHref={moduleHref}
          />
        ))}
      </Table>

      <NewSetDialog open={adding} onOpenChange={setAdding} />
    </>
  )
}

function SetRows({
  set,
  open,
  onToggle,
  moduleHref,
}: {
  set: MetadataPicklist
  open: boolean
  onToggle: () => void
  moduleHref: (moduleKey: string) => string
}) {
  const updatePicklist = useUpdatePicklist()

  return (
    <>
      <Row muted={!set.active}>
        <td>
          <button onClick={onToggle} className="text-muted-foreground hover:text-foreground">
            {open ? <ChevronDownIcon className="size-4" /> : <ChevronRightIcon className="size-4" />}
          </button>
        </td>
        <td>
          <button onClick={onToggle} className="font-medium hover:underline">
            {set.label ?? set.picklist_key}
          </button>
          <div>
            <Mono>{set.picklist_key}</Mono>
          </div>
        </td>
        <td>{set.values.filter((v) => v.active).length}</td>
        <td>
          {set.field_count === 0 ? (
            <span className="text-muted-foreground text-xs">no fields</span>
          ) : (
            `${set.field_count} field${set.field_count === 1 ? '' : 's'}`
          )}
        </td>
        <td>
          <StatusBadge active={set.active} />
        </td>
        <td className="text-right">
          <Button
            size="sm"
            variant="ghost"
            title={
              set.active && set.field_count > 0
                ? 'Fields still use this — publish will refuse until they are repointed'
                : undefined
            }
            onClick={() =>
              updatePicklist.mutate({
                picklistKey: set.picklist_key,
                patch: { active: !set.active },
              })
            }
          >
            {set.active ? 'Deactivate' : 'Activate'}
          </Button>
        </td>
      </Row>

      {open && (
        <tr className="bg-muted/20 border-t">
          <td />
          <td colSpan={5} className="px-3 py-3">
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
              <div>
                <p className="mb-1 text-xs font-medium">Choices</p>
                <ChoicesEditor picklist={set} />
              </div>
              <div>
                <p className="mb-1 text-xs font-medium">Used in</p>
                {set.used_by.length === 0 ? (
                  <p className="text-muted-foreground text-xs">No field uses this set yet.</p>
                ) : (
                  <ul className="space-y-0.5 text-sm">
                    {set.used_by.map((user) => (
                      <li key={user.definition_id}>
                        <Link to={moduleHref(user.module_key)} className="text-link hover:underline">
                          {user.module_label}
                        </Link>
                        <span className="text-muted-foreground"> · </span>
                        {user.label}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function NewSetDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const createPicklist = useCreatePicklist()
  const [name, setName] = useState('')
  const [choices, setChoices] = useState('')
  const [error, setError] = useState<string | null>(null)

  const close = (next: boolean) => {
    if (!next) {
      setName('')
      setChoices('')
      setError(null)
    }
    onOpenChange(next)
  }

  const submit = async () => {
    setError(null)
    try {
      await createPicklist.mutateAsync({
        label: name.trim(),
        is_global: true,
        values: choiceLines(choices),
      })
      close(false)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New global set</DialogTitle>
          <DialogDescription>A list of choices several fields can share.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="set_name">Name</Label>
            <Input
              id="set_name"
              value={name}
              placeholder="Industry"
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="set_choices">Choices</Label>
            <Textarea
              id="set_choices"
              rows={6}
              value={choices}
              placeholder={'One choice per line'}
              onChange={(e) => setChoices(e.target.value)}
            />
            <p className="text-muted-foreground text-xs">
              A field uses the set by choosing it under Choices in the field.
            </p>
          </div>
          {error && <p className="text-destructive text-sm">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => close(false)}>
            Cancel
          </Button>
          <Button
            disabled={!name.trim() || choiceLines(choices).length === 0 || createPicklist.isPending}
            onClick={submit}
          >
            Create global set
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
