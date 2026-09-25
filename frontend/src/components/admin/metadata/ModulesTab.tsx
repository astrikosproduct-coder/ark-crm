import { useState } from 'react'
import { Link } from 'react-router-dom'
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
import {
  useCreateModule,
  useMetadataModules,
  useUpdateModule,
  type MetadataModule,
} from '@/lib/metadata'

/**
 * Setup → Customization → Modules and Fields: the module list.
 *
 * Every module the register has, built or not — nothing is hidden (24 Sep
 * 2026). Its label opens it on Fields · Layout · Unused fields (and Conversion
 * Mapping, on a pipeline module); `moduleHref` says where, so this folder does
 * not name Setup's addresses. A module Setup files under another
 * (`setup_parent` — Deal Registrations, Conflicts and Partner Scorecards under
 * Partners) is listed directly beneath it, indented.
 */
export function ModulesTab({ moduleHref }: { moduleHref: (moduleKey: string) => string }) {
  const { data: modules = [], isLoading, isError, error } = useMetadataModules()
  const updateModule = useUpdateModule()
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [label, setLabel] = useState('')

  if (isLoading) return <LoadingRow what="modules" />
  if (isError) return <ErrorBox error={error} />

  const ordered = withChildrenUnderParents(modules)

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
            <th>Label</th>
            <th className="w-48">Key</th>
            <th className="w-16">#</th>
            <th className="w-24">Sections</th>
            <th className="w-24">Fields</th>
            <th className="w-24">Unused</th>
            <th className="w-24">Status</th>
            <th className="w-44" />
          </>
        }
      >
        {ordered.map((module) => (
          <Row key={module.module_key} muted={!module.active}>
            <td className={module.setup_parent ? 'pl-8 font-medium' : 'font-medium'}>
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
                <>
                  <Link to={moduleHref(module.module_key)} className="text-link hover:underline">
                    {module.label}
                  </Link>
                  {module.setup_parent && (
                    <span className="text-muted-foreground block text-xs font-normal">
                      under {modules.find((m) => m.module_key === module.setup_parent)?.label ?? module.setup_parent}
                    </span>
                  )}
                </>
              )}
            </td>
            <td>
              <Mono>{module.module_key}</Mono>
            </td>
            <td>
              <Mono>{module.sort_order}</Mono>
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

/**
 * The list in sort order, except that each Setup child follows its parent —
 * in its own sort order — so Partners' three sit together under it.
 */
function withChildrenUnderParents(modules: MetadataModule[]): MetadataModule[] {
  const keys = new Set(modules.map((m) => m.module_key))
  const isChild = (m: MetadataModule) => Boolean(m.setup_parent && keys.has(m.setup_parent))
  return modules
    .filter((m) => !isChild(m))
    .flatMap((parent) => [
      parent,
      ...modules.filter((m) => isChild(m) && m.setup_parent === parent.module_key),
    ])
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
