import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { PlusIcon, Trash2Icon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { FieldControl } from '@/components/form/FieldControl'
import { childFieldSyncFor, childSpecFor, compileForChildRow, type ResolvedChildColumn } from '@/lib/spec/childSpec'
import { type Values } from '@/lib/spec/conditions'
import { evaluate } from '@/lib/spec/evaluate'
import { useRecordForm } from '@/hooks/useRecordForm'
import { api } from '@/lib/api'
import type { ChildFieldSync, FieldSpec } from '@/types/field'

interface Props {
  field: FieldSpec
}

/**
 * A childlist renders as an editable table whose columns come from child_spec
 * in spec/extensions.json.
 *
 * No column, label, width or control is written here. A cell renders through
 * FieldControl — the same control layer every other field on the screen uses —
 * with the row supplied as its scope. Writing table-sized inputs instead would
 * give the prototype two control layers that drift apart on the first fix.
 *
 * Not one of the six childlists in the register declares a row shape, so every
 * child_spec is origin: "inferred" and every one of them carries a "proposed
 * shape" chip beside its label (rendered by FieldRow) and a row on Spec Health.
 * The table working does not close the gap.
 */
export function ChildListTable({ field }: Props) {
  const form = useRecordForm()
  const spec = childSpecFor(field)
  const sync = childFieldSyncFor(field)
  const [confirmingRow, setConfirmingRow] = useState<number | null>(null)

  if (!spec) {
    return (
      <div className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
        <span className="font-medium text-foreground">Row shape not defined.</span>{' '}
        {field.unexpressed ?? 'The field register does not say what columns this table holds.'}
      </div>
    )
  }

  const { columns } = spec
  const rows = form.children[field.api_name] ?? []
  const readOnly = spec.readonly || form.mode === 'view'
  const errors = form.childErrors[field.api_name] ?? []

  const setRows = (next: Values[]) => form.setChildRows(field.api_name, next)

  const update = (index: number, apiName: string, value: unknown) => {
    setRows(rows.map((r, i) => (i === index ? { ...r, [apiName]: value } : r)))
  }

  const addRow = () => setRows([...rows, {}])
  const deleteRow = (index: number) => {
    setRows(rows.filter((_, i) => i !== index))
    setConfirmingRow(null)
  }

  return (
    <div className="space-y-2">
      {spec.orphanedColumns.length > 0 && (
        <p className="text-xs text-amber-700 dark:text-amber-400">
          {spec.orphanedColumns.length} column{spec.orphanedColumns.length === 1 ? '' : 's'} in
          child_spec name a field the register no longer carries and {spec.orphanedColumns.length === 1 ? 'was' : 'were'}{' '}
          dropped — see Spec Health.
        </p>
      )}

      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <colgroup>
            {columns.map((c) => (
              <col key={c.key} style={c.width ? { minWidth: `${c.width}px` } : undefined} />
            ))}
            {!readOnly && <col style={{ width: '48px' }} />}
          </colgroup>

          <thead className="bg-muted/50">
            <tr>
              {columns.map((c) => (
                <th key={c.key} className="px-3 py-2 text-left font-medium whitespace-nowrap">
                  {c.field.description ? (
                    <Tooltip>
                      <TooltipTrigger type="button" className="cursor-help">
                        {c.field.label}
                      </TooltipTrigger>
                      <TooltipContent className="max-w-xs">{c.field.description}</TooltipContent>
                    </Tooltip>
                  ) : (
                    c.field.label
                  )}
                  {c.required && (
                    <span className="text-destructive" aria-hidden>
                      *
                    </span>
                  )}
                </th>
              ))}
              {!readOnly && <th className="w-12" aria-label="Actions" />}
            </tr>
          </thead>

          <tbody>
            {rows.length === 0 && (
              <tr>
                <td
                  colSpan={columns.length + (readOnly ? 0 : 1)}
                  className="px-3 py-4 text-center text-muted-foreground"
                >
                  {readOnly ? 'Nothing linked' : 'No rows yet'}
                </td>
              </tr>
            )}

            {rows.map((row, i) => (
              <tr key={i} className="border-t align-top">
                {sync && !readOnly && (
                  <ChildRowSync
                    sync={sync}
                    triggerValue={row[sync.trigger_column]}
                    row={row}
                    onFill={(patch) => setRows(rows.map((r, ri) => (ri === i ? { ...r, ...patch } : r)))}
                  />
                )}
                {columns.map((c) => {
                  const cellError = errors.find((e) => e.row === i && e.api_name === c.field.api_name)
                  return (
                    <td key={c.key} className="px-2 py-1.5">
                      <FieldControl
                        field={c.field}
                        scope={{
                          value:
                            c.field.type === 'computed'
                              ? computedCellValue(c, columns, row, form.values)
                              : row[c.field.api_name],
                          set: (v) => update(i, c.field.api_name, v),
                          invalid: Boolean(cellError),
                          mode: readOnly ? 'view' : 'edit',
                          id: `${field.module}.${field.api_name}.${i}.${c.field.api_name}`,
                        }}
                      />
                      {cellError && (
                        <p className="mt-1 text-xs text-destructive">{cellError.message}</p>
                      )}
                    </td>
                  )
                })}

                {!readOnly && (
                  <td className="px-2 py-1.5">
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="size-8"
                      onClick={() => setConfirmingRow(i)}
                    >
                      <Trash2Icon className="size-4" />
                      <span className="sr-only">Remove {spec.row_noun} {i + 1}</span>
                    </Button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!readOnly && (
        <Button type="button" variant="outline" size="sm" onClick={addRow}>
          <PlusIcon className="size-4" />
          {spec.add_label}
        </Button>
      )}

      {field.values_note && (
        <p className="text-xs text-muted-foreground">{field.values_note}</p>
      )}

      {/* Deleting a row throws away typed data that nothing else holds, so it
          confirms — the same posture the rest of the prototype takes on a
          destructive action. */}
      <Dialog open={confirmingRow !== null} onOpenChange={(open) => !open && setConfirmingRow(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Remove this {spec.row_noun}?</DialogTitle>
            <DialogDescription>
              {confirmingRow !== null && describeRow(columns, rows[confirmingRow] ?? {})}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setConfirmingRow(null)}>
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={() => confirmingRow !== null && deleteRow(confirmingRow)}
            >
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

/**
 * Logic-only, mounted once per row when the childlist declares a
 * child_field_sync (see leads.demo_attendees) — fetches the record the
 * trigger column names and, once it arrives, gap-fills every mirrored
 * column of THIS row that is still empty. Never overwrites a column the
 * row already carries. Renders nothing; `onFill` is the row's own `update`,
 * scoped by the caller to this row's index.
 *
 * Runs only when `target`/`targetId` change — not on every keystroke into a
 * mirrored column afterwards, which is what makes a manually-diverged value
 * stick instead of being silently overwritten back to the contact's own.
 */
function ChildRowSync({
  sync,
  triggerValue,
  row,
  onFill,
}: {
  sync: ChildFieldSync
  triggerValue: unknown
  row: Values
  onFill: (patch: Values) => void
}) {
  const targetId = typeof triggerValue === 'string' ? triggerValue : undefined

  const { data: target } = useQuery({
    queryKey: ['record', sync.target_module, targetId],
    queryFn: async () => (await api.get<Values>(`/${sync.target_module}/${targetId}`)).data,
    enabled: Boolean(targetId),
  })

  useEffect(() => {
    if (!target) return
    const patch: Values = {}
    for (const [rowColumn, targetField] of Object.entries(sync.mirror)) {
      if (!row[rowColumn] && target[targetField]) patch[rowColumn] = target[targetField]
    }
    if (Object.keys(patch).length > 0) onFill(patch)
    // row/onFill deliberately excluded — see the doc comment above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, targetId])

  return null
}

/**
 * A computed column has no per-row engine of its own — computeAll only derives
 * record-level values. The same computed_expr is evaluated once per row here,
 * reading an identifier from the row first and falling back to the record's own
 * values, so a column can read a sibling column (a bank guarantee's value) or a
 * record-level field (the contract value) with one expression syntax.
 */
function computedCellValue(
  column: ResolvedChildColumn,
  columns: ResolvedChildColumn[],
  row: Values,
  recordValues: Values
): unknown {
  const expr = column.field.computed_expr
  if (!expr) return null
  try {
    const ast = compileForChildRow(column.field.module, columns, expr)
    return evaluate(
      ast,
      { get: (name) => row[name] ?? recordValues[name] ?? null },
      expr
    )
  } catch (error) {
    console.error(`[spec] child row computed_expr failed for ${column.field.qref}`, error)
    return null
  }
}

/** Enough of a row to recognise it in the delete confirmation. */
function describeRow(columns: ResolvedChildColumn[], row: Values): string {
  const filled = columns
    .map((c) => row[c.field.api_name])
    .filter((v) => v !== null && v !== undefined && v !== '')
    .slice(0, 3)
    .map((v) => String(v))

  return filled.length
    ? `${filled.join(' · ')} — this cannot be undone.`
    : 'This row is empty. Removing it cannot be undone.'
}
