import { FieldControl } from '@/components/form/FieldControl'
import { RecordFormProvider } from '@/hooks/useRecordForm'
import { stageOf } from '@/lib/pipeline'
import type { Values } from '@/lib/spec/conditions'
import { historyOnlyNamesOf, reasonFieldsOf, stageScopedKey, stagesRecorded } from '@/lib/stageScope'
import { cn } from '@/lib/utils'
import type { FieldSpec } from '@/types/field'

function isBlank(v: unknown): boolean {
  if (Array.isArray(v)) return v.length === 0
  return v === null || v === undefined || v === ''
}

/**
 * The read-only per-stage surface on a pipeline record.
 *
 * ONE OF THEM NOW. There were three, and each was a hand-built form with its
 * own debounced save firing as the user typed:
 *
 *   "RECORDED AT STAGE n"   editable reason boxes under the stage section, a
 *                           second form several fields below the question that
 *                           raised them. Retired in A2 — the reasons are
 *                           anchored to the field that asks for them and drawn
 *                           by the ordinary RecordForm (lib/spec/anchors.ts).
 *
 *   StageMetricsStrip       Expected Close Month, plus Progression % and
 *   (and its chips)         Probability % and the override justification.
 *                           Retired in this pass. They are ordinary fields in
 *                           the register's HEADER section now, drawn by
 *                           RecordForm at the top of the stage tab and saved by
 *                           its Save button. Every keystroke used to cost a
 *                           record PUT, a refetch, and a remount of every form
 *                           on the screen; a section costs one request when the
 *                           user is finished. Carry-forward and per-stage
 *                           writing are untouched — those were always the
 *                           projection in useRecordForm, never these strips.
 *
 * What is left is ReasonsPanel: READ-ONLY, every reason and justification the
 * record carries, at every stage it was given one. Not an input, and never
 * meant to be two — the boxes are inline, this is the record of what went
 * into them.
 */

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
    <div className="bg-card rounded-lg shadow-sm">
      <div className="border-b px-4 py-3">
        <span className="text-section font-bold tracking-wide">REASONS &amp; JUSTIFICATIONS</span>
      </div>

      <div className="space-y-4 px-4 py-4">
        {answered.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            Nothing to explain yet. A reason is asked for when the record is put on hold, closed
            lost, given a Progression % or Probability % other than its stage's, or moved to a stage
            that is not the next one.
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
    <div className="bg-raised flex flex-wrap items-baseline gap-x-3 gap-y-1 rounded-md px-4 py-2.5">
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
