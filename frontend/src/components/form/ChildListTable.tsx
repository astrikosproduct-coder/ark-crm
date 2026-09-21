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
import { cn } from '@/lib/utils'
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

  const defaults = spec.row_defaults

  /** What a row takes when its `by` column is set to this value. */
  const presetFor = (value: unknown): Values =>
    (defaults && typeof value === 'string' ? (defaults.values[value] as Values | undefined) : undefined) ?? {}

  const isEmpty = (v: unknown) => v === undefined || v === null || v === ''

  const update = (index: number, apiName: string, value: unknown) => {
    setRows(
      rows.map((r, i) => {
        if (i !== index) return r
        const next: Values = { ...r, [apiName]: value }
        // Choosing the milestone fills in its percentage and trigger. A
        // DEFAULT, not a rule: a column the row already carries is left as it
        // was typed, and both stay editable afterwards.
        if (defaults && apiName === defaults.by) {
          for (const [column, preset] of Object.entries(presetFor(value))) {
            if (isEmpty(next[column])) next[column] = preset
          }
        }
        return next
      })
    )
  }

  const addRow = () => setRows([...rows, {}])

  /** Every standard row the table does not already carry, in declared order. */
  const missingDefaults = defaults
    ? Object.entries(defaults.values).filter(([key]) => !rows.some((r) => r[defaults.by] === key))
    : []
  const addAllDefaults = () =>
    setRows([...rows, ...missingDefaults.map(([key, preset]) => ({ [defaults!.by]: key, ...(preset as Values) }))])

  // Summed, never enforced — see ChildSpec.total_columns.
  const totals = spec.total_columns
    .map((apiName) => ({
      column: columns.find((c) => c.field.api_name === apiName),
      sum: rows.reduce((running, r) => running + (Number(r[apiName]) || 0), 0),
    }))
    .filter((t): t is { column: ResolvedChildColumn; sum: number } => Boolean(t.column))
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

      {/* No outer box and no vertical rules — columns are separated by the
          space between them. The only stroke left is the hairline under the
          header row; rows are told apart by the alternating raised ground,
          which is the same layer their inputs sit on. */}
      <div className="overflow-x-auto">
        <table className="w-full border-separate border-spacing-0 text-sm">
          <colgroup>
            {columns.map((c) => (
              <col key={c.key} style={c.width ? { minWidth: `${c.width}px` } : undefined} />
            ))}
            {!readOnly && <col style={{ width: '48px' }} />}
          </colgroup>

          <thead className="text-label">
            <tr>
              {columns.map((c) => (
                <th
                  key={c.key}
                  className="border-border text-muted-foreground border-b px-4 pt-1 pb-2.5 text-left font-semibold whitespace-nowrap"
                >
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
              {!readOnly && (
                <th className="border-border w-12 border-b" aria-label="Actions" />
              )}
            </tr>
          </thead>

          <tbody>
            {rows.length === 0 && (
              <tr>
                <td
                  colSpan={columns.length + (readOnly ? 0 : 1)}
                  className="px-4 py-5 text-center text-muted-foreground"
                >
                  {readOnly ? 'Nothing linked' : 'No rows yet'}
                </td>
              </tr>
            )}

            {rows.map((row, i) => (
              <tr key={i} className="align-top even:bg-raised/60">
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
                    <td key={c.key} className="px-4 py-2.5">
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
                  <td className="px-4 py-2.5">
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
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" onClick={addRow}>
            <PlusIcon className="size-4" />
            {spec.add_label}
          </Button>
          {missingDefaults.length > 0 && (
            <Button type="button" variant="ghost" size="sm" onClick={addAllDefaults}>
              {defaults?.add_all_label ?? 'Add the standard rows'}
              <span className="text-muted-foreground">({missingDefaults.length})</span>
            </Button>
          )}
        </div>
      )}

      {rows.length > 0 &&
        totals.map(({ column, sum }) => (
          <p
            key={column.key}
            className={cn(
              'text-xs',
              sum === 100 ? 'text-muted-foreground' : 'text-amber-700 dark:text-amber-400'
            )}
          >
            {column.field.label} totals {sum}%
            {sum === 100 ? '' : ' — the rows do not add up to 100%.'}
          </p>
        ))}

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
