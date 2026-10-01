import { useState } from 'react'
import { ChevronDownIcon, Undo2Icon } from 'lucide-react'

import { errorMessage } from '@/lib/admin'
import { cn } from '@/lib/utils'
import {
  typeLabel,
  useMetadataFields,
  useRestoreField,
  useRestorePlacement,
  type MetadataField,
} from '@/lib/metadata'

/**
 * Unused Items — the fields taken off this module, in the layout's left rail
 * under NEW SECTION, where Zoho keeps them (Setup rebuild, 4b, 1 Oct 2026; it
 * was a tab of its own, and before that a Deleted fields screen for every
 * module). Each comes back with one click; 4c makes that a drag onto the form.
 *
 * Every one still exists with its configuration intact, and its column — or
 * its key in the module's custom field store — still holds every value
 * recorded against it. Restoring is un-hiding, not re-creating.
 *
 * TWO WAYS A FIELD GETS HERE, TWO WAYS BACK
 * - The field was DELETED (definition_status 'deleted'): Restore brings it
 *   back on every module that deletion took it off — POST
 *   /fields/{definition_id}/restore.
 * - Only this module's placement was REMOVED: Restore puts it back here and
 *   nowhere else — POST /placements/{placement_id}/restore.
 * Until 25 Sep 2026 the screen sent the placement id to the field endpoint;
 * the two ids come from different sequences.
 */
export function UnusedItems({ moduleKey }: { moduleKey: string }) {
  const { data: fields = [] } = useMetadataFields(moduleKey, 'deleted')
  const restoreField = useRestoreField()
  const restorePlacement = useRestorePlacement()
  const [open, setOpen] = useState(true)
  const [failed, setFailed] = useState<string | null>(null)
  const busy = restoreField.isPending || restorePlacement.isPending

  const restore = async (field: MetadataField) => {
    setFailed(null)
    try {
      if (field.definition_status === 'deleted') await restoreField.mutateAsync(field.definition_id)
      else await restorePlacement.mutateAsync(field.placement_id)
    } catch (err) {
      setFailed(errorMessage(err))
    }
  }

  return (
    <div className="border-t pt-3">
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
              className="border-input bg-input-bg flex items-center gap-1.5 rounded-md border px-2 py-1.5 text-xs"
              title={typeLabel(field.field_type)}
            >
              <span className="min-w-0 flex-1 truncate">{field.label}</span>
              <button
                type="button"
                disabled={busy}
                title="Put it back on the form"
                aria-label={`Restore ${field.label}`}
                className="text-muted-foreground hover:text-foreground disabled:opacity-40"
                onClick={() => restore(field)}
              >
                <Undo2Icon className="size-3.5" />
              </button>
            </div>
          ))}
          {failed && <p className="text-destructive text-xs">{failed}</p>}
        </div>
      )}
    </div>
  )
}
