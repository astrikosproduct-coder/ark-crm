import { useState } from 'react'
import { ArrowDownIcon, ArrowUpIcon, PlusIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { errorMessage } from '@/lib/admin'
import {
  COUNTRY_CODE_SET,
  useCreatePicklistValue,
  useReorderPicklistValues,
  useUpdatePicklistValue,
  type MetadataPicklist,
} from '@/lib/metadata'

/**
 * The choices of one list, edited in place — inside a field's dialog for the
 * field's own list, and under Global Sets for a shared one. Zoho has no screen
 * of its own for these (Setup rebuild, 25 Sep 2026); this is what the old
 * Picklists tab's expanded row became.
 *
 * Every change is written to the draft as it is made, not on the dialog's
 * Save — a choice added and then Cancelled away would otherwise be half-there.
 *
 * WHY A CHOICE IS NEVER DELETED, ONLY DEACTIVATED: its key is what records
 * store (PARTNER_SOURCED, not "Partner-sourced"), and what the register's own
 * conditions compare against. Deleting it would leave every record holding it
 * pointing at nothing. The label is free to change; the key is made from the
 * first label and then fixed. A choice the CRM's own rules read — Open, On
 * Hold, Converted — can be renamed and never deactivated (the server refuses).
 */
export function ChoicesEditor({ picklist }: { picklist: MetadataPicklist }) {
  const updateValue = useUpdatePicklistValue()
  const createValue = useCreatePicklistValue()
  const reorder = useReorderPicklistValues()
  const [adding, setAdding] = useState('')
  const [error, setError] = useState<string | null>(null)

  const run = async (action: () => Promise<unknown>) => {
    setError(null)
    try {
      await action()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const move = (valueId: number, delta: number) => {
    const ids = picklist.values.map((v) => v.id)
    const index = ids.indexOf(valueId)
    const target = index + delta
    if (index < 0 || target < 0 || target >= ids.length) return
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    run(() => reorder.mutateAsync(ids))
  }

  const add = () => {
    const label = adding.trim()
    if (!label) return
    run(async () => {
      await createValue.mutateAsync({ picklist_key: picklist.picklist_key, label })
      setAdding('')
    })
  }

  return (
    <div className="rounded-md border">
      <table className="w-full text-sm">
        <tbody>
          {picklist.values.map((value, index) => (
            <tr key={value.id} className="border-b last:border-b-0 [&>td]:px-2 [&>td]:py-1">
              <td className="w-12">
                <div className="flex items-center gap-0.5">
                  <button
                    type="button"
                    title="Move up"
                    disabled={index === 0}
                    className="text-muted-foreground hover:text-foreground disabled:opacity-30"
                    onClick={() => move(value.id, -1)}
                  >
                    <ArrowUpIcon className="size-3" />
                  </button>
                  <button
                    type="button"
                    title="Move down"
                    disabled={index === picklist.values.length - 1}
                    className="text-muted-foreground hover:text-foreground disabled:opacity-30"
                    onClick={() => move(value.id, 1)}
                  >
                    <ArrowDownIcon className="size-3" />
                  </button>
                </div>
              </td>
              <td className={value.active ? undefined : 'text-muted-foreground'}>
                <InlineLabel
                  value={value.label}
                  title={`Stored as ${value.key}`}
                  onSave={(label) =>
                    run(() => updateValue.mutateAsync({ valueId: value.id, patch: { label } }))
                  }
                />
              </td>
              <td className="w-40 text-right">
                {!value.active && <Badge variant="outline">Inactive</Badge>}
                {value.is_system && (
                  <Badge
                    variant="secondary"
                    title="The CRM's own rules read this choice. It can be renamed, not deactivated."
                  >
                    Used by the CRM
                  </Badge>
                )}
              </td>
              <td className="w-24 text-right">
                {!(value.is_system && value.active) && (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="h-7"
                    onClick={() =>
                      run(() =>
                        updateValue.mutateAsync({
                          valueId: value.id,
                          patch: { active: !value.active },
                        })
                      )
                    }
                  >
                    {value.active ? 'Deactivate' : 'Activate'}
                  </Button>
                )}
              </td>
            </tr>
          ))}
          <tr className="[&>td]:px-2 [&>td]:py-1">
            <td />
            <td colSpan={3}>
              <div className="flex gap-2">
                <Input
                  className="h-7"
                  placeholder={
                    picklist.picklist_key === COUNTRY_CODE_SET
                      ? 'Country and code, like Germany (+49)'
                      : 'New choice'
                  }
                  value={adding}
                  onChange={(e) => setAdding(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      add()
                    }
                  }}
                />
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="h-7"
                  disabled={!adding.trim() || createValue.isPending}
                  onClick={add}
                >
                  <PlusIcon className="size-3" />
                  Add choice
                </Button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      {error && <p className="text-destructive px-2 pb-2 text-sm">{error}</p>}
    </div>
  )
}

function InlineLabel({
  value,
  title,
  onSave,
}: {
  value: string
  title?: string
  onSave: (label: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)

  if (!editing) {
    return (
      <button
        type="button"
        title={title}
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
    if (draft.trim() && draft.trim() !== value) onSave(draft.trim())
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
        if (e.key === 'Enter') {
          e.preventDefault()
          save()
        }
        if (e.key === 'Escape') setEditing(false)
      }}
    />
  )
}
