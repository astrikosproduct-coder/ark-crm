import { useState } from 'react'
import { Undo2Icon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { ErrorBox, LoadingRow, Mono, Row, Table } from './shared'
import { errorMessage } from '@/lib/admin'
import { useMetadataFields, useRestoreField, type MetadataField } from '@/lib/metadata'

/**
 * Fields an admin has deleted, and the button that brings them back.
 *
 * Every row here still exists in field_metadata with its configuration intact,
 * and the business column each one describes still exists in PostgreSQL with
 * every value still in it. That is what makes this screen meaningful rather
 * than decorative: restoring is not re-creating from scratch, it is un-hiding
 * something that was never destroyed, and the data reappears with it.
 *
 * NOT THE SAME THING AS VERSION ROLLBACK
 * ---------------------------------------
 * Restoring here brings back ONE field and moves nothing else. Rolling back a
 * version (see the Publish tab) returns the ENTIRE configuration to an earlier
 * snapshot. The two are separate operations on purpose.
 */
export function DeletedFieldsTab() {
  const { data: fields = [], isLoading, isError, error } = useMetadataFields(undefined, 'deleted')
  const restore = useRestoreField()
  const [failed, setFailed] = useState<string | null>(null)

  if (isLoading) return <LoadingRow what="deleted fields" />
  if (isError) return <ErrorBox error={error} />

  return (
    <>
      <p className="text-muted-foreground mb-3 max-w-3xl text-sm">
        Deleting a field never drops a database column and never deletes a stored value.
        Everything listed here can be restored with its previous configuration, and the data
        already recorded against it becomes visible again at the next publish.
      </p>

      {fields.length === 0 ? (
        <p className="text-muted-foreground py-8 text-sm">
          No deleted fields. Anything deleted from the Fields tab appears here.
        </p>
      ) : (
        <Table
          head={
            <>
              <th className="w-32">Module</th>
              <th>Field</th>
              <th className="w-56">Section</th>
              <th className="w-28">Type</th>
              <th className="w-44">Deleted</th>
              <th className="w-28" />
            </>
          }
        >
          {fields.map((field: MetadataField) => (
            <Row key={field.id}>
              <td>
                <Mono>{field.module_key}</Mono>
              </td>
              <td>
                <div className="font-medium">{field.label}</div>
                <Mono>{field.api_name}</Mono>
              </td>
              <td className="text-muted-foreground text-xs">{field.section_label}</td>
              <td>
                <Mono>{field.field_type}</Mono>
              </td>
              <td className="text-muted-foreground text-xs">
                {field.deleted_at ? new Date(field.deleted_at).toLocaleString() : '—'}
                {field.deleted_by && <div>by {field.deleted_by}</div>}
              </td>
              <td className="text-right">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={restore.isPending}
                  onClick={async () => {
                    setFailed(null)
                    try {
                      await restore.mutateAsync(field.id)
                    } catch (err) {
                      setFailed(errorMessage(err))
                    }
                  }}
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
