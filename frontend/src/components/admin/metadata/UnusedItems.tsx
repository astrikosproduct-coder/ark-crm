import { useState } from 'react'
import { ChevronDownIcon } from 'lucide-react'

import { cn } from '@/lib/utils'
import { typeLabel, type MetadataField } from '@/lib/metadata'
import { DRAG } from './layoutDraft'

/**
 * Unused Items — the fields taken off this module, in the layout editor's left
 * rail under NEW SECTION, where Zoho keeps them (Setup rebuild, 4b/4c).
 *
 * Drag one onto the form to put it back; drag a field from the form onto this
 * list to take it off. Nothing happens until the editor's Save, which brings a
 * field back as it was — its column, or its key in the module's custom field
 * store, kept every value recorded against it — and a field deleted everywhere
 * comes back as a field again.
 */
export function UnusedItems({
  fields,
  onDropField,
}: {
  fields: MetadataField[]
  /** A field from the form dropped here: take it off the form. */
  onDropField: (placementId: number) => void
}) {
  const [open, setOpen] = useState(true)
  const [over, setOver] = useState(false)

  return (
    <div
      className={cn('rounded-md border-t pt-3', over && 'ring-primary/50 ring-2')}
      onDragOver={(e) => {
        if (!e.dataTransfer.types.includes(DRAG.cell)) return
        e.preventDefault()
        e.dataTransfer.dropEffect = 'move'
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        setOver(false)
        const id = Number(e.dataTransfer.getData(DRAG.cell))
        if (!id) return
        e.preventDefault()
        onDropField(id)
      }}
    >
      <button
        type="button"
        className="mb-2 flex items-center gap-1.5 text-sm font-semibold"
        onClick={() => setOpen((v) => !v)}
      >
        Unused Items
        <ChevronDownIcon className={cn('size-4 transition-transform', !open && '-rotate-90')} />
        <span className="bg-accent rounded-full px-2 text-xs">{fields.length}</span>
      </button>

      {open && (
        <div className="space-y-1">
          {fields.length === 0 && (
            <p className="text-muted-foreground text-xs">A field you remove waits here.</p>
          )}
          {fields.map((field) => (
            <div
              key={field.placement_id}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.effectAllowed = 'move'
                e.dataTransfer.setData(DRAG.unused, String(field.placement_id))
                e.dataTransfer.setData('text/plain', field.label)
              }}
              className="border-input bg-input-bg cursor-grab truncate rounded-md border px-2 py-1.5 text-xs active:cursor-grabbing"
              title={`${typeLabel(field.field_type)} — drag onto the form to put it back`}
            >
              {field.label}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
