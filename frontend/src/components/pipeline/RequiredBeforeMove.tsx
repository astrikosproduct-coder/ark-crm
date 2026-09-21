import { useEffect, useMemo, useState } from 'react'

import { FieldRow } from '@/components/form/FieldRow'
import { RecordFormProvider, useRecordForm } from '@/hooks/useRecordForm'
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

/** What the fields filled in the dialog add to the stage move's own request. */
export interface MoveFieldsState {
  /** The values typed here, in the request's shape (per-stage keys included). */
  patch: Values
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
 */
export function RequiredBeforeMove({
  module,
  recordId,
  values,
  from,
  skipped,
  onChange,
}: {
  module: string
  recordId: string
  values: Values
  from: number
  skipped?: readonly number[]
  onChange: (state: MoveFieldsState) => void
}) {
  const stageScope = useMemo(() => ({ stage: from, currentStage: from, skipped }), [from, skipped])
  return (
    <RecordFormProvider module={module} mode="edit" recordId={recordId} initialValues={values} stageScope={stageScope}>
      <MoveFields module={module} from={from} skipped={skipped} onChange={onChange} />
    </RecordFormProvider>
  )
}

function MoveFields({
  module,
  from,
  skipped,
  onChange,
}: {
  module: string
  from: number
  skipped?: readonly number[]
  onChange: (state: MoveFieldsState) => void
}) {
  const form = useRecordForm()
  const missing = useMemo(
    () => requiredBeforeMove(module, form.values, from, from + 1, skipped),
    [module, form.values, from, skipped]
  )
  const [shown, setShown] = useState<string[]>(() => missing.map((f) => f.api_name))

  // A condition can make a new field required as the person types (Deal
  // Source -> Partner-sourced). It joins the list; nothing ever leaves it.
  useEffect(() => {
    const extra = missing.map((f) => f.api_name).filter((name) => !shown.includes(name))
    if (extra.length) setShown((names) => [...names, ...extra])
  }, [missing, shown])

  useEffect(() => {
    const payload = form.toPayload()
    const patch: Values = {}
    for (const [key, value] of Object.entries(payload)) {
      if (shown.some((name) => key === name || key.startsWith(`${name}__s`))) patch[key] = value
    }
    onChange({ patch, remaining: missing.length })
    // toPayload is rebuilt on every edit, so form.values is the trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.values, shown, missing.length])

  if (shown.length === 0) return null
  const fields = fieldsOf(module).filter((f) => shown.includes(f.api_name))
  return (
    <div className="space-y-2 rounded-md border p-3">
      <p className="text-sm">
        {missing.length > 0
          ? `Fill in ${missing.length === 1 ? 'this required field' : `these ${missing.length} required fields`} to leave Stage ${from}.`
          : `Stage ${from} is complete. These are saved with the move.`}
      </p>
      <div className="@container">
        <div className="grid gap-x-10 gap-y-4">
          {fields.map((field) => (
            <FieldRow key={field.qref} field={field} requiredNow />
          ))}
        </div>
      </div>
    </div>
  )
}
