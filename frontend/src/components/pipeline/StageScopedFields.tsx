import { useRef } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { TriangleAlertIcon } from 'lucide-react'

import { FieldControl } from '@/components/form/FieldControl'
import { RecordFormProvider } from '@/hooks/useRecordForm'
import { api } from '@/lib/api'
import { fieldsOf } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'
import { stageOf } from '@/lib/pipeline'
import {
  carryForwardFieldsOf,
  historyOnlyNamesOf,
  probabilityBandBreach,
  reasonFieldsOf,
  stageScopedKey,
  stageScopedPatch,
  stageScopedValue,
  stagesRecorded,
} from '@/lib/stageScope'
import { cn } from '@/lib/utils'
import type { FieldSpec } from '@/types/field'

/**
 * The per-stage surfaces on a pipeline record.
 *
 * TWO OF THEM NOW, and the split changed in Phase A3. There used to be a
 * "RECORDED AT STAGE n" panel of editable reason boxes sitting under the stage
 * section — a second form, with its own save, several fields below the question
 * that raised it. The reasons are anchored to the status field and rendered by
 * the ordinary RecordForm since A2 (see lib/spec/anchors.ts), so what is left
 * here is:
 *
 *   StageMetricsStrip   Progression %, Probability % and Expected Close Month
 *                       above every stage, written immediately — plus, when
 *                       the probability typed falls outside the stage's band,
 *                       the justification for it. Asked here because this strip
 *                       is the only surface that owns that number.
 *
 *   ReasonsPanel        READ-ONLY. Every reason and justification the record
 *                       carries, at every stage it was given one. Not an input
 *                       and never was meant to be two: the boxes are inline,
 *                       this is the record of what went into them.
 *
 * The strip writes IMMEDIATELY, debounced, exactly like HeaderStrip — no Edit
 * button, no Save. Deliberate rather than convenient: a per-stage value belongs
 * to the stage the user is looking at, and routing it through the stage editor
 * would put it inside a form whose payload covers the whole record.
 *
 * Its RecordFormProvider exists purely so FieldControl has the context hook it
 * always calls. Every value and every write goes through `scope`, never through
 * the provider's state, so nothing here becomes a draft. The provider's record
 * id is namespaced so it cannot collide with the real edit form's draft for the
 * same record — same trick, same reason, as HeaderStrip.
 */

const SAVE_DEBOUNCE_MS = 300

interface Common {
  module: string
  collection: string
  recordId: string
  values: Values
  /** The stage on screen — which may not be the stage the record is at. */
  stage: number
  /** The stage the record is actually at. */
  currentStage: number
  readOnly: boolean
}

function useStagePatch(collection: string, recordId: string) {
  const queryClient = useQueryClient()
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({})

  const save = useMutation({
    mutationFn: async (patch: Values) => (await api.put(`/${collection}/${recordId}`, patch)).data,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['record', collection, recordId] }),
        queryClient.invalidateQueries({ queryKey: ['list', collection] }),
        queryClient.invalidateQueries({ queryKey: ['collection', collection] }),
      ])
    },
  })

  return (key: string, patch: Values) => {
    clearTimeout(timers.current[key])
    timers.current[key] = setTimeout(() => save.mutate(patch), SAVE_DEBOUNCE_MS)
  }
}

function isBlank(v: unknown): boolean {
  if (Array.isArray(v)) return v.length === 0
  return v === null || v === undefined || v === ''
}

// --------------------------------------------------------------- the strip

/**
 * The carry-forward fields above the stage's own, on every stage: Progression
 * %, Probability % and Expected Close Month.
 *
 * Carry-forward: a stage the user has never touched shows the nearest earlier
 * stage's value, so moving forward does not blank boxes that were just filled
 * in. Editing writes THIS stage's value; the earlier stage keeps what it was
 * given, which is what turns a single value into a history.
 *
 * Which fields are here is spec — extensions.json stage_scoped.carry_forward —
 * so nothing in this component names one, and the date that joined the two
 * percentages needed no code beyond the control width below.
 */
export function StageMetricsStrip(props: Common) {
  const fields = carryForwardFieldsOf(props.module)
  if (fields.length === 0 || !props.recordId) return null

  return (
    <RecordFormProvider
      module={props.module}
      mode="edit"
      recordId={`stage:${props.stage}:${props.recordId}`}
    >
      <StripBody {...props} fields={fields} />
    </RecordFormProvider>
  )
}

function StripBody({
  module,
  collection,
  recordId,
  fields,
  values,
  stage,
  currentStage,
  readOnly,
}: Common & { fields: FieldSpec[] }) {
  const patch = useStagePatch(collection, recordId)

  // Playbook §3.1: a probability outside the stage's band has to be justified
  // in writing. The register gives the justification row no
  // visibility_condition because until Probability became editable per stage
  // there was no moment at which to ask — there is one now, and it is here,
  // next to the number that caused it. See extensions.json sticky.extra.
  const breach = probabilityBandBreach(module, values, stage)
  const justification = fieldsOf(module).find(
    (f) => f.api_name === 'probability_override_justification'
  )
  const written = justification
    ? values[stageScopedKey(justification.api_name, stage)]
    : undefined
  const showJustification = Boolean(justification) && (Boolean(breach) || !isBlank(written))

  return (
    <div className="bg-muted/20 mb-3 rounded-lg border px-4 py-2.5">
      <div className="flex flex-wrap items-center gap-x-8 gap-y-2">
        {fields.map((field) => {
          const value = stageScopedValue(module, field, values, stage)
          // "Carried forward" means the box is showing a number that belongs to
          // an earlier stage. Saying so is the difference between a sensible
          // default and a value the user believes was entered here.
          const carried = isBlank(values[stageScopedKey(field.api_name, stage)])
          const history = stagesRecorded(field, values).filter((s) => s !== stage)

          return (
            <div key={field.qref} className="flex min-w-0 items-center gap-2">
              <span className="text-muted-foreground shrink-0 text-xs font-medium">
                {field.label}
              </span>
              {/* w-24 fits a percentage and truncates a date. The strip held
                  two numbers until Expected Close Month joined it, so the
                  width follows the control rather than the other way round. */}
              <div className={cn('shrink-0', field.type === 'date' ? 'w-40' : 'w-24')}>
                <FieldControl
                  field={field}
                  scope={{
                    value: value ?? '',
                    set: (v) =>
                      patch(field.api_name, stageScopedPatch(field, stage, currentStage, v)),
                    mode: readOnly ? 'view' : 'edit',
                    id: `stage.${stage}.${field.qref}`,
                  }}
                />
              </div>
              {carried && !isBlank(value) && (
                <span className="text-muted-foreground/70 shrink-0 text-[11px]">
                  carried forward
                </span>
              )}
              {history.length > 0 && (
                <span
                  className="text-muted-foreground/70 shrink-0 text-[11px]"
                  title={history
                    .map((s) => `Stage ${s}: ${String(values[stageScopedKey(field.api_name, s)])}`)
                    .join(' · ')}
                >
                  {history.length} earlier
                </span>
              )}
            </div>
          )
        })}
      </div>

      {showJustification && justification && (
        <div className="border-warning/40 mt-2.5 space-y-1.5 border-t pt-2.5">
          <label
            className="flex flex-wrap items-center gap-1.5 text-sm font-medium"
            htmlFor={`stage.${stage}.${justification.qref}`}
          >
            <TriangleAlertIcon className="text-warning size-4 shrink-0" />
            {justification.label}
            {breach && <span className="text-destructive">*</span>}
          </label>
          {breach && (
            <p className="text-muted-foreground text-xs">
              {breach.pct}% is outside the {breach.min}–{breach.max}% band Stage {stage} allows.
              Playbook §3.1 asks for that in writing, and the answer stays with Stage {stage}.
            </p>
          )}
          <FieldControl
            field={justification}
            scope={{
              value: written ?? '',
              set: (v) =>
                patch(
                  justification.api_name,
                  stageScopedPatch(justification, stage, currentStage, v)
                ),
              mode: readOnly ? 'view' : 'edit',
              id: `stage.${stage}.${justification.qref}`,
            }}
          />
        </div>
      )}
    </div>
  )
}

// -------------------------------------------------------- the reasons panel

/**
 * READ-ONLY. Every reason this record has given, at every stage it gave one.
 *
 * WHY THIS IS NOT A DUPLICATE OF THE INLINE BOXES
 * ------------------------------------------------
 * The inline box is the INPUT and can only ever show one stage: it sits beside
 * the status field on the stage tab you are looking at, and On Hold Reason
 * there means "why this lead is on hold as of Stage 3". This panel is the
 * RECORD. A lead held at Stage 0, released, and held again at Stage 3 has two
 * different answers, and only one surface can show both.
 *
 * That is also why it is read-only, and why it is on the Details tab rather
 * than under the stage. An editable copy would be a second place to write one
 * answer — the exact thing extensions.json rejected for Stage Skip Reason, and
 * the exact thing this panel replaced: the old "RECORDED AT STAGE n" panel was
 * editable, had its own save, and sat several fields below the question that
 * raised it.
 *
 * Three fields appear here and nowhere else, because a box for them would be
 * that second place: Stage Skip Reason and Stage Reversal Reason are written by
 * the Advance / Change stage dialog, and Probability Override Justification by
 * the metrics strip above.
 */
export function ReasonsPanel({
  module,
  values,
  onOpenStage,
  onOpenHistory,
}: {
  module: string
  values: Values
  /** Jump to the stage tab that owns an answer. */
  onOpenStage?: (stage: number) => void
  /** Jump to the transition log, for the two the dialog writes. */
  onOpenHistory?: () => void
}) {
  const fields = reasonFieldsOf(module)
  if (fields.length === 0) return null

  const historyOnly = historyOnlyNamesOf(module)

  const entries = fields.map((field) => ({
    field,
    recordLevel: historyOnly.has(field.api_name),
    stages: historyOnly.has(field.api_name) ? [] : stagesRecorded(field, values),
    plain: values[field.api_name],
  }))

  const answered = entries.filter((e) =>
    e.recordLevel ? !isBlank(e.plain) : e.stages.length > 0
  )

  return (
    <div className="rounded-lg border">
      <div className="flex flex-wrap items-baseline gap-x-2 border-b px-4 py-3">
        <span className="text-section font-bold tracking-wide">REASONS &amp; JUSTIFICATIONS</span>
        <span className="text-muted-foreground text-xs">
          {answered.length === 0
            ? 'nothing recorded'
            : `${answered.length} of ${entries.length} recorded`}{' '}
          · read-only
        </span>
      </div>

      <div className="space-y-4 px-4 py-4">
        <p className="text-muted-foreground text-xs">
          What this record has been asked to explain, and what it answered. Each answer belongs to
          the stage it was given at and is shown here alongside the others — the box you type in
          sits beside the question that raised it, never here.
        </p>

        {answered.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            Nothing to explain yet. A reason is asked for when the record is put on hold, closed
            lost, moved out of its probability band, or moved to a stage that is not the next one.
          </p>
        ) : (
          <RecordFormProvider module={module} mode="view" recordId="reasons">
            <dl className="space-y-4">
              {answered.map(({ field, recordLevel, stages, plain }) => (
                <div key={field.qref} className="space-y-1.5">
                  <dt className="text-sm font-medium">{field.label}</dt>
                  <dd className="space-y-1.5">
                    {recordLevel ? (
                      <ReasonRow
                        field={field}
                        value={plain}
                        caption="recorded with the stage change"
                        onOpen={onOpenHistory}
                        openLabel="History"
                      />
                    ) : (
                      stages.map((stage) => (
                        <ReasonRow
                          key={stage}
                          field={field}
                          value={values[stageScopedKey(field.api_name, stage)]}
                          caption={`Stage ${stage}${stageOf(stage) ? ` · ${stageOf(stage)!.name}` : ''}`}
                          onOpen={onOpenStage ? () => onOpenStage(stage) : undefined}
                          openLabel="Open"
                        />
                      ))
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          </RecordFormProvider>
        )}
      </div>
    </div>
  )
}

/**
 * One answer. Rendered through FieldControl in view mode rather than as raw
 * text, so a picklist reads as its label and a date as `dd MMM yyyy` — the same
 * formatting the field has everywhere else, from the same code.
 */
function ReasonRow({
  field,
  value,
  caption,
  onOpen,
  openLabel,
}: {
  field: FieldSpec
  value: unknown
  caption: string
  onOpen?: () => void
  openLabel: string
}) {
  return (
    <div className="bg-muted/20 flex flex-wrap items-baseline gap-x-3 gap-y-1 rounded-md border px-3 py-2">
      <span className="text-muted-foreground shrink-0 text-xs font-medium">{caption}</span>
      <div className={cn('min-w-0 flex-1 text-sm')}>
        <FieldControl
          field={field}
          scope={{ value: value ?? '', set: () => {}, mode: 'view', id: `reason.${field.qref}` }}
        />
      </div>
      {onOpen && (
        <button
          type="button"
          onClick={onOpen}
          className="text-muted-foreground hover:text-foreground shrink-0 text-xs underline underline-offset-2"
        >
          {openLabel}
        </button>
      )}
    </div>
  )
}
