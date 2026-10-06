import { useState } from 'react'
import { GripVerticalIcon, PlusIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { errorMessage } from '@/lib/admin'
import { cn } from '@/lib/utils'
import { DRAG } from './layoutDraft'
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
 *
 * Order is set by DRAGGING a choice by its handle (Setup 4e, 5 Oct 2026) —
 * the same gesture as the layout editor, in place of the up/down arrows. The
 * new order is written to the draft on drop.
 */
export function ChoicesEditor({ picklist }: { picklist: MetadataPicklist }) {
  const updateValue = useUpdatePicklistValue()
  const createValue = useCreatePicklistValue()
  const reorder = useReorderPicklistValues()
  const [adding, setAdding] = useState('')
  const [error, setError] = useState<string | null>(null)
  // The row a dragged choice would land before, for the drop line.
  const [overId, setOverId] = useState<number | null>(null)

  const run = async (action: () => Promise<unknown>) => {
    setError(null)
    try {
      await action()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  /** Put `valueId` just before `beforeId` (or last), and save the order. */
  const moveBefore = (valueId: number, beforeId: number | null) => {
    if (valueId === beforeId) return
    const rest = picklist.values.map((v) => v.id).filter((id) => id !== valueId)
    const at = beforeId === null ? -1 : rest.indexOf(beforeId)
    const ids = at < 0 ? [...rest, valueId] : [...rest.slice(0, at), valueId, ...rest.slice(at)]
    if (ids.every((id, i) => id === picklist.values[i]?.id)) return
    run(() => reorder.mutateAsync(ids))
  }
  const dropProps = (beforeId: number | null) => ({
    onDragOver: (e: React.DragEvent) => {
      if (!e.dataTransfer.types.includes(DRAG.choice)) return
      e.preventDefault()
      setOverId(beforeId ?? -1)
    },
    onDragLeave: () => setOverId(null),
    onDrop: (e: React.DragEvent) => {
      setOverId(null)
      const id = Number(e.dataTransfer.getData(DRAG.choice))
      if (!id) return
      e.preventDefault()
      moveBefore(id, beforeId)
    },
  })

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
          {picklist.values.map((value) => (
            <tr
              key={value.id}
              {...dropProps(value.id)}
              className={cn(
                'border-b last:border-b-0 [&>td]:px-2 [&>td]:py-1',
                overId === value.id && 'border-t-primary border-t-2'
              )}
            >
              <td className="w-8">
                <span
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.effectAllowed = 'move'
                    e.dataTransfer.setData(DRAG.choice, String(value.id))
                    e.dataTransfer.setData('text/plain', value.label)
                  }}
                  className="text-muted-foreground hover:text-foreground flex cursor-grab active:cursor-grabbing"
                  title="Drag to reorder"
                >
                  <GripVerticalIcon className="size-3.5" />
                </span>
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
          <tr
            {...dropProps(null)}
            className={cn('[&>td]:px-2 [&>td]:py-1', overId === -1 && 'border-t-primary border-t-2')}
          >
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
