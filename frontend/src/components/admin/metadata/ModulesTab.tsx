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
import { ErrorBox, LoadingRow, Row, StatusSwitch, Table } from './shared'
import { date as fmtDate } from '@/lib/format'
import { errorMessage } from '@/lib/admin'
import {
  useCreateModule,
  useMetadataModules,
  useUpdateModule,
  withChildrenUnderParents,
} from '@/lib/metadata'

/**
 * Setup → Customization → Modules and Fields: the module list.
 *
 * Zoho's columns (Setup rebuild, 4b, 1 Oct 2026): the module's name, opening
 * it; its fields; Last Modified; and a Status switch. Every module the register
 * has, built or not — nothing is hidden (24 Sep 2026). `moduleHref` says where
 * a module opens, so this folder does not name Setup's addresses. A module
 * Setup files under another (`setup_parent` — Deal Registrations, Conflicts and
 * Partner Scorecards under Partners) is listed directly beneath it, indented.
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
          A module cannot be deleted — its fields point at it. Switch it off instead.
        </p>
        <Button size="sm" onClick={() => setAdding(true)}>
          <PlusIcon className="size-4" />
          Create New Module
        </Button>
      </div>

      <Table
        head={
          <>
            <th>Module</th>
            <th className="w-24">Fields</th>
            <th className="w-44">Last Modified</th>
            <th className="w-24">Status</th>
            <th className="w-24" />
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
            <td>{module.field_count}</td>
            <td>{module.last_modified ? fmtDate(module.last_modified) : '—'}</td>
            <td>
              <StatusSwitch
                checked={module.active}
                label={`${module.label} is ${module.active ? 'on' : 'off'}`}
                disabled={updateModule.isPending}
                onChange={(active) =>
                  updateModule.mutate({ moduleKey: module.module_key, patch: { active } })
                }
              />
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
  const [label, setLabel] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setError(null)
    try {
      await createModule.mutateAsync({ label: label.trim() })
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
          <DialogTitle>Create a module</DialogTitle>
          <DialogDescription>
            It starts empty. Add its sections and fields on its layout.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="module_label">Module name</Label>
            <Input
              id="module_label"
              value={label}
              placeholder="Activities and Documents"
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
            disabled={!label.trim() || createModule.isPending}
            onClick={submit}
          >
            Create module
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
