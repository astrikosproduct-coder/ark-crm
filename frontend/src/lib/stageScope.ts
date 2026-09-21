import extensionsData from '../../spec/extensions.json'
import { fieldsOf } from '@/lib/spec'
import type { Values } from '@/lib/spec/conditions'
import { resolverFor } from '@/lib/spec/resolvers'
import type { FieldSpec } from '@/types/field'

/**
 * Fields recorded PER STAGE rather than once per record.
 *
 * WHY THIS EXISTS
 * ---------------
 * The register has one column per field and one value per record, which cannot
 * express either of the two things reviewers asked for:
 *
 *   CARRY_FORWARD — Expected Close Month is revised at every stage. A stage
 *   inherits the previous stage's answer as its starting point, but writing at
 *   Stage 3 must not rewrite what Stage 1 was told. (Progression % and
 *   Probability % were carry-forward until 0022; they follow the stage now.)
 *
 *   STICKY — a CROSS-CUTTING reason (On Hold Reason, Stage Skip Reason…) is
 *   captured at the stage where its condition became true, and must NOT be
 *   carried forward. A lead put on hold at Stage 1 and again at Stage 3 has two
 *   different reasons; showing the Stage 1 answer in the Stage 3 box invites the
 *   user to leave it there, and the record then claims a reason that was never
 *   given for the second hold.
 *
 * Which fields behave which way is spec, not code — see extensions.json
 * stage_scoped, and the `stage_scoped` row in open_questions asking the workbook
 * to grow a column for it.
 *
 * STORAGE. `<api_name>__s<stage>` — expected_close_month__s3. The suffix is a key on
 * the ordinary record, so nothing in the store, MSW, the API client or the query
 * layer needed a new concept. A carry_forward field ALSO writes the plain
 * api_name when the stage being edited is the record's current one, so list
 * columns and the readiness panel keep reading one number and know nothing
 * about any of this. A sticky field never writes it:
 * there is no single "the" on-hold reason to write.
 */

/**
 * WHAT IS LEFT OF THE SIDECAR AFTER B2, AND WHY.
 *
 * WHICH fields are per-stage, and whether each carries forward or sticks, are
 * register columns now — `stage_scoped` on every row of spec/fields.json. The
 * rule that used to derive that set from sections and conditions is gone, and
 * with it the reason an admin could not make one field sticky without editing
 * a file that silently caught four others.
 *
 * These three could not go with it, because each names a FUNCTION rather than
 * describing a field, and an admin cannot write a function:
 *
 *   default_by     a resolver in lib/spec/resolvers.ts, seeding an untouched
 *                  box. Nothing uses one today; no formula can guess a close
 *                  month, which is why expected_close_month has none.
 *   history_only   Stage Skip / Stage Reversal Reason. NOT per-stage at all:
 *                  the transitions table already carries one reason per move,
 *                  and the field on the record is the latest of them. Listed
 *                  here so no form offers a second box for one.
 */
interface CarryForwardField {
  api_name: string
  /** A resolver name in lib/spec/resolvers.ts. Seeds an untouched box only. */
  default_by?: string
}

interface StageScopedSpec {
  /**
   * Which modules render the strip and the Reasons panel. A SCREEN question,
   * not a storage one — which is why it did not move into the register with
   * `stage_scoped`. modules.is_pipeline would answer it identically today.
   */
  modules: string[]
  /** Only for `default_by`. The SET is fields.json's stage_scoped now. */
  carry_forward: { fields: CarryForwardField[] }
  /** Written by the transition dialog; no form offers a box for them. */
  history_only?: { fields: string[] }
}

const spec = (extensionsData as unknown as { stage_scoped?: StageScopedSpec }).stage_scoped ?? {
  modules: [],
  carry_forward: { fields: [] },
}

// DERIVED — the 'computed'/'autonumber' exclusion — lived here until B2. It
// was part of the rule that DERIVED the sticky set from a section name; the
// set is a column now, so the exclusion was applied once, at absorption, and
// has nothing left to exclude on every render.

/** True when this module renders the per-stage strip and the sticky panel. */
export function isStageScopedModule(module: string): boolean {
  return spec.modules.includes(module)
}

/** Where a per-stage value lives on the record. */
export function stageScopedKey(apiName: string, stage: number): string {
  return `${apiName}__s${stage}`
}

/*
 * carryForwardFieldsOf() lived here until the strips were retired. It answered
 * "which fields does the metrics strip draw", and there is no metrics strip:
 * the three carry-forward fields are in the register's HEADER section and the
 * ordinary form draws them from their placement, in the order an admin set by
 * dragging. Nothing needs a second list of them.
 */

/*
 * stickyFieldsOf() lived here until Phase A3, and what replaced it is worth
 * recording rather than just deleting.
 *
 * It answered "which reasons should the panel under this stage offer a box
 * for", by evaluating each field's visibility_condition against the SAVED
 * record. That is the design flaw, not an implementation detail: a saved record
 * is what the form has already been submitted as, so the box could not appear
 * until after a save, and the panel had to exist as a second form with a second
 * save to hold it. The reasons are anchored to the status field now and drawn
 * by the ordinary RecordForm, whose isVisible runs against LIVE form state — so
 * the question and the answer are in one form and one save. See
 * lib/spec/anchors.ts.
 *
 * It also carried an `answered` clause: keep offering a field whose condition
 * has since gone away, if this stage already answered it, so that taking a lead
 * off hold did not hide the reason it was put on hold. That is no longer a
 * special case. The inline box disappears with its condition, exactly as a
 * conditional field should, and the answer is read back in ReasonsPanel, which
 * lists every stage that ever answered and is not driven by conditions at all.
 */

/**
 * True when this field's VALUE is recorded per stage — `<api_name>__s<n>`.
 *
 * A STORAGE question, not a rendering one, and the two stopped being the same
 * question in Phase A2. Before anchors, every stage-scoped field was drawn by
 * a surface of its own and hidden from the form, so one predicate answered
 * both; an anchored reason is still stored per stage and is now drawn by the
 * ordinary RecordForm. Ask hiddenFromFormNamesOf() what a form must not draw —
 * it is derived from this, minus the anchored ones, plus the transition-written
 * ones. Do not use this one to decide visibility.
 *
 * WHY THE NAME CHANGED (B0.2)
 * ---------------------------
 * It was isStageScoped(), and the Phase A review called for collapsing it into
 * hiddenFromFormNamesOf() as two predicates answering nearly the same question.
 * They are not: this one is asked by useRecordForm to decide which values get
 * projected through `__s<n>`, and that one is asked by PipelineRecordPage to
 * decide what the form must not draw. Merging them would recreate exactly the
 * conflation A2 removed. What was actually wrong was four names in one
 * `stageScoped*` family with only the docstrings saying which axis each sits
 * on, so the storage pair is named for storage now and the rendering pair for
 * rendering. isStageScopedModule() keeps its name: it answers neither
 * question, only whether the module has stages at all.
 */
export function isPerStageValue(module: string, field: FieldSpec): boolean {
  if (!isStageScopedModule(module)) return false
  return field.stage_scoped !== 'none'
}

/** Every api_name this module renders per stage rather than in a section. */
export function perStageValueNamesOf(module: string): Set<string> {
  return new Set(fieldsOf(module).filter((f) => isPerStageValue(module, f)).map((f) => f.api_name))
}

/**
 * What the box for `field` at `stage` should show.
 *
 * Sticky: only this stage's own value, ever. Carry-forward: this stage's value,
 * else the nearest EARLIER stage that has one, else the plain api_name (every
 * record written before this mechanism existed), else the field's default_by
 * resolver.
 */
export function stageScopedValue(
  module: string,
  field: FieldSpec,
  values: Values,
  stage: number
): unknown {
  const own = values[stageScopedKey(field.api_name, stage)]
  if (!isEmpty(own)) return own

  const entry = spec.carry_forward.fields.find((f) => f.api_name === field.api_name)
  if (!entry) return undefined

  for (let s = stage - 1; s >= 0; s--) {
    const earlier = values[stageScopedKey(field.api_name, s)]
    if (!isEmpty(earlier)) return earlier
  }

  const base = values[field.api_name]
  if (!isEmpty(base)) return base

  const resolve = resolverFor(entry.default_by)
  return resolve ? resolve(module, values) : undefined
}

/**
 * The patch a per-stage edit sends.
 *
 * The base api_name is written only when the stage being edited is the stage the
 * record is actually AT — editing Stage 1 on a record sitting at Stage 3 is
 * correcting history, and history must not become the record's current value.
 */
export function stageScopedPatch(
  field: FieldSpec,
  stage: number,
  currentStage: number,
  value: unknown
): Values {
  const patch: Values = { [stageScopedKey(field.api_name, stage)]: value }
  // A carry-forward field ALSO writes the plain api_name at the record's
  // current stage, so list columns and the readiness engine keep reading one
  // number. A sticky field never does: there is no single "the" reason.
  const carried = field.stage_scoped === 'carry_forward'
  if (carried && stage === currentStage) patch[field.api_name] = value
  return patch
}

/** Every stage that has ever been given a value for this field, ascending. */
export function stagesRecorded(field: FieldSpec, values: Values): number[] {
  const prefix = `${field.api_name}__s`
  return Object.keys(values)
    .filter((k) => k.startsWith(prefix) && !isEmpty(values[k]))
    .map((k) => Number(k.slice(prefix.length)))
    .filter((n) => Number.isInteger(n))
    .sort((a, b) => a - b)
}

function isEmpty(v: unknown): boolean {
  if (Array.isArray(v)) return v.length === 0
  return v === null || v === undefined || v === ''
}

// ------------------------------------------------- what a form must not draw

/**
 * Fields the record keeps but no form asks for — see `history_only`.
 *
 * Stage Skip Reason and Stage Reversal Reason are written by the Advance /
 * Change stage dialog when it records the transition. They were ALSO rendering
 * as ordinary editable boxes in CROSS-CUTTING on the Details tab, which is two
 * places to write one answer: type a different reason there and the record and
 * the transition log disagree, with nothing to say which is true.
 *
 * They are not stage-scoped. The transitions table already carries one reason
 * per move, and the field on the record is the latest of them.
 */
export function historyOnlyNamesOf(module: string): Set<string> {
  const names = new Set<string>()
  if (!isStageScopedModule(module)) return names
  const byName = new Set(fieldsOf(module).map((f) => f.api_name))
  for (const name of spec.history_only?.fields ?? []) {
    if (byName.has(name)) names.add(name)
  }
  return names
}

/**
 * Every reason and justification on this module, whether per-stage or not.
 *
 * What the read-only Reasons & Justifications panel lists. Deliberately the
 * union of things that are asked in different places — inline beside the
 * status or the number, and in the transition dialog — because
 * the point of the panel is that the RECORD's answers are all in one place
 * even though its QUESTIONS are not.
 */
export function reasonFieldsOf(module: string): FieldSpec[] {
  const scoped = perStageValueNamesOf(module)
  const history = historyOnlyNamesOf(module)
  return fieldsOf(module).filter(
    (f) =>
      (scoped.has(f.api_name) && f.stage_scoped !== 'carry_forward') ||
      history.has(f.api_name)
  )
}

/**
 * What a pipeline form must not draw, because another surface draws it.
 *
 * ONE ENTRY LEFT, AND IT IS NOT A RENDERING PREFERENCE
 * ----------------------------------------------------
 * This used to subtract the anchored reasons from the per-stage set and hide
 * everything that remained — Expected Close Month, Progression %, Probability %
 * and the override justification — because each had a hand-built strip of its
 * own above the tabs. Those strips are gone: the four are ordinary fields in
 * the HEADER section now, drawn by RecordForm and saved by the same Save button
 * as every other field, with the justification anchored to the number that
 * demands it. Per-stage reading and writing is unchanged; it was never the
 * strips that did that, it was the projection in useRecordForm.
 *
 * What stays hidden is what a form genuinely cannot own: Stage Skip Reason and
 * Stage Reversal Reason are written by the Advance / Change stage dialog as
 * part of the move itself, and the transitions table already carries one per
 * move. A second box for them would be a second place to write one answer.
 */
export function hiddenFromFormNamesOf(module: string): Set<string> {
  return historyOnlyNamesOf(module)
}
