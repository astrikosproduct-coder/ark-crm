import { useState } from 'react'
import { Undo2Icon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { ErrorBox, LoadingRow, Row, Table } from './shared'
import { errorMessage } from '@/lib/admin'
import { dateTime as fmtDateTime } from '@/lib/format'
import {
  useMetadataFields,
  useRestoreField,
  typeLabel,
  useRestorePlacement,
  type MetadataField,
} from '@/lib/metadata'

/**
 * Unused fields — the fields taken off one module, and the button that brings
 * each back. Zoho's name for it; this was the Deleted fields tab, across every
 * module, until the Setup rebuild put it under the module it belongs to.
 *
 * Every row still exists in field_definitions / field_placements with its
 * configuration intact, and the business column (or custom_fields key) each
 * one describes still holds every value recorded against it. That is what
 * makes this screen meaningful rather than decorative: restoring is not
 * re-creating from scratch, it is un-hiding something that was never destroyed.
 *
 * TWO WAYS A FIELD GETS HERE, TWO WAYS BACK
 * -----------------------------------------
 * - The field was DELETED (definition_status 'deleted'): Restore brings the
 *   field back, on every module that deletion took it off — POST
 *   /fields/{definition_id}/restore.
 * - Only this module's placement was REMOVED: Restore puts it back here and
 *   nowhere else — POST /placements/{placement_id}/restore.
 * Until 25 Sep 2026 this screen sent the placement id to the field endpoint,
 * which restored whichever deleted field happened to have that number, or
 * nothing. The two ids come from different sequences.
 *
 * NOT THE SAME THING AS VERSION ROLLBACK: restoring here brings back one field
 * and moves nothing else; rolling back (Developer Space → Versions) returns the
 * entire configuration to an earlier snapshot.
 */
export function UnusedFieldsTab({ moduleKey }: { moduleKey: string }) {
  const { data: fields = [], isLoading, isError, error } = useMetadataFields(moduleKey, 'deleted')
  const restoreField = useRestoreField()
  const restorePlacement = useRestorePlacement()
  const [failed, setFailed] = useState<string | null>(null)

  if (isLoading) return <LoadingRow what="unused fields" />
  if (isError) return <ErrorBox error={error} />

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
    <>
      <p className="text-muted-foreground mb-3 max-w-3xl text-sm">
        Taking a field off never drops a database column and never deletes a stored value.
        Everything listed here can be restored with its previous configuration, and the data
        already recorded against it becomes visible again at the next publish.
      </p>

      {fields.length === 0 ? (
        <p className="text-muted-foreground py-8 text-sm">
          No unused fields. A field deleted on the Fields tab appears here.
        </p>
      ) : (
        <Table
          head={
            <>
              <th>Field</th>
              <th className="w-56">Section</th>
              <th className="w-28">Type</th>
              <th className="w-44">Taken off</th>
              <th className="w-28" />
            </>
          }
        >
          {fields.map((field) => (
            <Row key={field.id}>
              <td>
                <div className="font-medium">{field.label}</div>
              </td>
              <td className="text-muted-foreground text-xs">{field.section_label}</td>
              <td>{typeLabel(field.field_type)}</td>
              <td className="text-muted-foreground text-xs">
                {field.deleted_at ? fmtDateTime(field.deleted_at) : '—'}
                {field.deleted_by && <div>by {field.deleted_by}</div>}
              </td>
              <td className="text-right">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={restoreField.isPending || restorePlacement.isPending}
                  onClick={() => restore(field)}
                >
                  <Undo2Icon className="size-3.5" />
                  Restore
                </Button>
              </td>
            </Row>
          ))}
        </Table>
      )}

      {failed && <p className="text-destructive mt-3 text-sm">{failed}</p>}
    </>
  )
}
