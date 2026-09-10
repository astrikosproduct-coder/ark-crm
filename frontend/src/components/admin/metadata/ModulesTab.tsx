import { useState } from 'react'
import { PlusIcon } from 'lucide-react'

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
import { useCreateModule, useMetadataModules, useUpdateModule } from '@/lib/metadata'

/**
 * The register's ten sheets.
 *
 * There is no `opportunities` row here and that is not a bug. The register
 * files every Stage 0-7 pipeline field under `leads`; the three-way split into
 * Leads, Opportunities and Deals is applied by the frontend at load time from
 * spec/module_split.json. This screen shows the register as it is, and the
 * Fields tab marks each field with where the split actually puts it.
 */
export function ModulesTab() {
  const { data: modules = [], isLoading, isError, error } = useMetadataModules()
  const updateModule = useUpdateModule()
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [label, setLabel] = useState('')

  if (isLoading) return <LoadingRow what="modules" />
  if (isError) return <ErrorBox error={error} />

  return (
    <>
      <div className="mb-3 flex items-center justify-between">
        <p className="text-muted-foreground max-w-2xl text-sm">
          One row per register sheet. A module cannot be deleted — fields point at it, and
          removing it would orphan them rather than hide them. Deactivate it instead.
        </p>
        <Button size="sm" onClick={() => setAdding(true)}>
          <PlusIcon className="size-4" />
          Add module
        </Button>
      </div>

      <Table
        head={
          <>
            <th className="w-16">#</th>
            <th className="w-48">Key</th>
            <th>Label</th>
            <th className="w-24">Sections</th>
            <th className="w-24">Fields</th>
            <th className="w-24">Deleted</th>
            <th className="w-24">Status</th>
            <th className="w-44" />
          </>
        }
      >
        {modules.map((module) => (
          <Row key={module.module_key} muted={!module.active}>
            <td>
              <Mono>{module.sort_order}</Mono>
            </td>
            <td>
              <Mono>{module.module_key}</Mono>
            </td>
            <td className="font-medium">
              {editing === module.module_key ? (
                <div className="flex gap-2">
                  <Input
                    className="h-8 w-56"
                    value={label}
                    autoFocus
                    onChange={(e) => setLabel(e.target.value)}
                  />
                  <Button
                    size="sm"
                    onClick={() => {
                      updateModule.mutate({
                        moduleKey: module.module_key,
                        patch: { label: label.trim() },
                      })
                      setEditing(null)
                    }}
                  >
                    Save
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>
                    Cancel
                  </Button>
                </div>
              ) : (
                module.label
              )}
            </td>
            <td>{module.section_count}</td>
            <td>{module.field_count}</td>
            <td>{module.deleted_field_count || <span className="text-muted-foreground">—</span>}</td>
            <td>
              <StatusBadge active={module.active} />
            </td>
            <td className="text-right">
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setEditing(module.module_key)
                  setLabel(module.label)
                }}
              >
                Rename
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  updateModule.mutate({
                    moduleKey: module.module_key,
                    patch: { active: !module.active },
                  })
                }
              >
                {module.active ? 'Deactivate' : 'Activate'}
              </Button>
            </td>
          </Row>
        ))}
      </Table>

      <AddModuleDialog open={adding} onOpenChange={setAdding} />
    </>
  )
}

function AddModuleDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const createModule = useCreateModule()
  const [key, setKey] = useState('')
  const [label, setLabel] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setError(null)
    try {
      await createModule.mutateAsync({ module_key: key.trim(), label: label.trim() })
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
          <DialogTitle>Add module</DialogTitle>
          <DialogDescription>
            A new register sheet. It will have no sections and no fields until you add them,
            and publish reports an empty module as a warning until it does.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="module_key">Key</Label>
            <Input
              id="module_key"
              value={key}
              placeholder="activities_docs"
              onChange={(e) => setKey(e.target.value)}
            />
            <p className="text-muted-foreground text-xs">
              Lower case, digits and underscores. Not editable afterwards — every field row
              names it.
            </p>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="module_label">Label</Label>
            <Input
              id="module_label"
              value={label}
              placeholder="Activities &amp; Documents"
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
            disabled={!/^[a-z][a-z0-9_]*$/.test(key.trim()) || !label.trim() || createModule.isPending}
            onClick={submit}
          >
            Add module
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
