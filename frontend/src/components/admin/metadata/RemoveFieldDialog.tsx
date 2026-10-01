import { useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Bullets } from '@/components/ui/notice'
import { errorMessage } from '@/lib/admin'
import { useDeleteField, useRemovePlacement, type MetadataField } from '@/lib/metadata'

/**
 * Zoho's "Remove Field", from a field's ··· menu on the layout (Setup rebuild,
 * 4b). This was the Fields table's Delete dialog; it moved with the editing.
 *
 * Both actions are logical and reversible — the column, or the custom_fields
 * key, and every value in it survive, and the field waits under Unused Items.
 * They differ only for a field also shown read-only on later modules of the
 * pipeline: "Remove from Leads" takes it off this module alone (the field is
 * kept, so it can be put back here); "Remove everywhere" deletes the field, and
 * restoring it later brings back exactly the modules this took it off. A field
 * on one module has just the one button — the distinction means nothing there.
 */
export function RemoveFieldDialog({
  field,
  moduleLabel,
  onClose,
}: {
  field: MetadataField | null
  moduleLabel: string
  onClose: () => void
}) {
  const removePlacement = useRemovePlacement()
  const deleteField = useDeleteField()
  const [error, setError] = useState<string | null>(null)

  const others = Math.max((field?.module_count ?? 1) - 1, 0)
  const busy = removePlacement.isPending || deleteField.isPending

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

  return (
    <Dialog open={Boolean(field)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Remove {field?.label}?</DialogTitle>
          <DialogDescription>It moves to Unused Items. Nothing stored is lost.</DialogDescription>
        </DialogHeader>

        <Bullets
          className="text-muted-foreground text-sm"
          items={[
            'Records keep every value they already hold.',
            'Restore it from Unused Items, and the values show again.',
            others > 0 &&
              `It is also shown on ${others} later module${others === 1 ? '' : 's'} of the pipeline.`,
            'It leaves the form at the next publish.',
          ]}
        />
        {error && <p className="text-destructive text-sm">{error}</p>}

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          {others > 0 ? (
            <>
              <Button variant="outline" disabled={busy} onClick={() => run('placement')}>
                Remove from {moduleLabel}
              </Button>
              <Button variant="destructive" disabled={busy} onClick={() => run('definition')}>
                Remove everywhere
              </Button>
            </>
          ) : (
            <Button variant="destructive" disabled={busy} onClick={() => run('placement')}>
              {busy ? 'Removing…' : 'Remove field'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
