import { useEffect, useMemo, useRef, useState } from 'react'

import { FieldRow } from '@/components/form/FieldRow'
import { RecordFormProvider, useRecordForm } from '@/hooks/useRecordForm'
import { revealField } from '@/lib/revealField'
import { fieldsOf } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'
import { missingDue } from '@/lib/spec/validation'
import type { FieldSpec } from '@/types/field'

/**
 * The required fields a forward move is waiting on — layer 1 of the four-layer
 * check, enforced since 21 Sep 2026.
 *
 * Leaving a stage needs its own required fields, and every earlier stage's,
 * filled in. The stage being entered asks for its fields when it is left. The
 * server refuses the same move (backend/app/requirements.py).
 */
export function requiredBeforeMove(
  module: string,
  values: Values,
  from: number,
  to: number,
  skipped: readonly number[] = []
): FieldSpec[] {
  if (to <= from) return []
  const missing = missingDue(module, values, { atStage: from, skipped })
  return fieldsOf(module).filter((f) => f.api_name in missing)
}

/**
 * A field the dialog can take as an input: one the record itself stores and a
 * person types. Not a formula, an id, a list of rows, or a value shown "From
 * the Lead" — those have nothing to type into here.
 */
export function canFillInMove(field: FieldSpec): boolean {
  return (
    field.value_mode !== 'read_through' &&
    !['computed', 'autonumber', 'childlist'].includes(field.type)
  )
}

/** Ask the panel to scroll to a field and focus it. `seq` repeats a request for the same field. */
export interface MoveFieldFocus {
  name: string
  seq: number
}

/** What the fields filled in the dialog add to the stage move's own request. */
export interface MoveFieldsState {
  /** The values typed here, in the request's shape (per-stage keys included). */
  patch: Values
  /** The record as it now reads with those typed values — what the checks below read. */
  values: Values
  /** Required fields still empty. The move waits until this is 0. */
  remaining: number
}

/**
 * The missing fields AS INPUTS, inside the Update Stage dialog — Zoho's
 * Blueprint (decided 21 Sep 2026). Nothing on the record page is marked red
 * for a stage's fields while it is being worked; when the person asks to move
 * on, the dialog asks for exactly what is missing, and the move saves them in
 * the same request.
 *
 * Its own form over the record, so conditions work as they do on the page:
 * pick Partner-sourced here and Customer (Partner / SI) appears. A field
 * stays on screen once shown, even after it is filled, so it doesn't vanish
 * from under the cursor.
 *
 * `pulledIn` adds fields a readiness check names (Oct 2026). Clicking a check
 * used to CLOSE the dialog and jump to the record — and everything typed here
 * went with it, because these values are saved only with the move. Now the
 * field comes to the dialog instead, and nothing typed is lost.
 */
export function RequiredBeforeMove({
  module,
  recordId,
  values,
  from,
  skipped,
  pulledIn = NONE,
  focus = null,
  onChange,
}: {
  module: string
  recordId: string
  values: Values
  from: number
  skipped?: readonly number[]
  /** Fields a readiness check named, brought in to be filled here. */
  pulledIn?: readonly string[]
  focus?: MoveFieldFocus | null
  onChange: (state: MoveFieldsState) => void
}) {
  const stageScope = useMemo(() => ({ stage: from, currentStage: from, skipped }), [from, skipped])
  return (
    <RecordFormProvider module={module} mode="edit" recordId={recordId} initialValues={values} stageScope={stageScope}>
      <MoveFields
        module={module}
        from={from}
        skipped={skipped}
        pulledIn={pulledIn}
        focus={focus}
        onChange={onChange}
      />
    </RecordFormProvider>
  )
}

const NONE: readonly string[] = []

function MoveFields({
  module,
  from,
  skipped,
  pulledIn,
  focus,
  onChange,
}: {
  module: string
  from: number
  skipped?: readonly number[]
  pulledIn: readonly string[]
  focus: MoveFieldFocus | null
  onChange: (state: MoveFieldsState) => void
}) {
  const form = useRecordForm()
  const box = useRef<HTMLDivElement>(null)
  const missing = useMemo(
    () => requiredBeforeMove(module, form.values, from, from + 1, skipped),
    [module, form.values, from, skipped]
  )
  const [shown, setShown] = useState<string[]>(() => missing.map((f) => f.api_name))

  // A condition can make a new field required as the person types (Deal
  // Source -> Partner-sourced), and a check can bring one in. Either joins the
  // list; nothing ever leaves it.
  useEffect(() => {
    const extra = [...missing.map((f) => f.api_name), ...pulledIn].filter((name) => !shown.includes(name))
    if (extra.length) setShown((names) => [...names, ...extra.filter((n, i) => extra.indexOf(n) === i)])
  }, [missing, pulledIn, shown])

  // Scroll to the field a check asked for, inside THIS panel — the record page
  // behind the dialog draws the same field first in the document.
  useEffect(() => {
    if (focus && box.current) revealField(focus.name, 2000, box.current)
  }, [focus])

  useEffect(() => {
    const payload = form.toPayload()
    const patch: Values = {}
    for (const [key, value] of Object.entries(payload)) {
      if (shown.some((name) => key === name || key.startsWith(`${name}__s`))) patch[key] = value
    }
    onChange({ patch, values: form.values, remaining: missing.length })
    // toPayload is rebuilt on every edit, so form.values is the trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.values, shown, missing.length])

  if (shown.length === 0) return null
  const fields = fieldsOf(module).filter((f) => shown.includes(f.api_name))
  const missingNames = new Set(missing.map((f) => f.api_name))
  return (
    <div ref={box} className="space-y-2 rounded-md border p-3">
      <p className="text-sm">
        {missing.length > 0
          ? `Fill in ${missing.length === 1 ? 'this required field' : `these ${missing.length} required fields`} to leave Stage ${from}.`
          : `Stage ${from} is complete. These are saved with the move.`}
      </p>
      <div className="@container">
        <div className="grid gap-x-10 gap-y-4">
          {fields.map((field) => (
            <FieldRow
              key={field.qref}
              field={field}
              requiredNow={missingNames.has(field.api_name) || !pulledIn.includes(field.api_name)}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
