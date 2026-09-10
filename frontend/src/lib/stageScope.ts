import extensionsData from '../../spec/extensions.json'
import stagesData from '../../spec/stages.json'
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
 *   CARRY_FORWARD — Progression % and Probability % sit at the top of every
 *   stage and are editable there. A stage inherits the previous stage's number
 *   as its starting point, but writing at Stage 3 must not rewrite what Stage 1
 *   was told. One value per record makes a probability history impossible: the
 *   number the deal was given at Demo is simply gone once Prescription edits it.
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
 * STORAGE. `<api_name>__s<stage>` — probability_pct__s3. The suffix is a key on
 * the ordinary record, so nothing in the store, MSW, the API client or the query
 * layer needed a new concept. A carry_forward field ALSO writes the plain
 * api_name when the stage being edited is the record's current one, so list
 * columns, the readiness panel and the probability-band check keep reading one
 * number and know nothing about any of this. A sticky field never writes it:
 * there is no single "the" on-hold reason to write.
 */

interface CarryForwardField {
  api_name: string
  /** A resolver name in lib/spec/resolvers.ts. Seeds an untouched box only. */
  default_by?: string
}

interface StickyExtra {
  api_name: string
  /** A predicate name in PREDICATES below. Same escape hatch as computed_by. */
  when: string
}

interface StageScopedSpec {
  modules: string[]
  carry_forward: { fields: CarryForwardField[] }
  sticky: { sections: string[]; require_condition?: boolean; extra?: StickyExtra[] }
  /** Written by the transition dialog; no form offers a box for them. */
  history_only?: { fields: string[] }
}

const spec = (extensionsData as unknown as { stage_scoped?: StageScopedSpec }).stage_scoped ?? {
  modules: [],
  carry_forward: { fields: [] },
  sticky: { sections: [] },
}

interface StageBand {
  stage: number
  prob_min: number | null
  prob_max: number | null
}

const BANDS = stagesData as unknown as StageBand[]

/**
 * A condition the expression language cannot reach.
 *
 * The probability entered for THIS stage against the band spec/stages.json
 * gives the stage. That is not a function of any field's value — the band is
 * not a field — so there is no expression that could say it, exactly as with
 * progression in lib/spec/resolvers.ts. extensions.json still names it, in
 * sticky.extra, as `when: "probability_out_of_band"`; until Administration can
 * express a rule like this the binding is one reviewed function, never an
 * eval().
 */
/** A probability outside its stage's band, with the numbers, or null. */
export interface BandBreach {
  pct: number
  min: number
  max: number
}

/**
 * Is the probability entered for THIS stage outside the band the stage allows?
 *
 * Returns the numbers rather than a boolean so the surface that asks can say
 * which band was missed and by how much — "62% is outside 10–20% for Stage 1"
 * is an explanation; "justification required" is a demand.
 */
export function probabilityBandBreach(
  module: string,
  values: Values,
  stage: number
): BandBreach | null {
  const field = fieldsOf(module).find((f) => f.api_name === 'probability_pct')
  if (!field) return null
  const raw = stageScopedValue(module, field, values, stage)
  const pct = typeof raw === 'number' ? raw : Number(raw)
  if (!Number.isFinite(pct)) return null

  const band = BANDS.find((b) => b.stage === stage)
  if (!band || band.prob_min === null || band.prob_max === null) return null
  if (pct >= band.prob_min && pct <= band.prob_max) return null
  return { pct, min: band.prob_min, max: band.prob_max }
}

/** Types nobody types into — a computed CROSS-CUTTING row is record-level. */
const DERIVED = new Set(['computed', 'autonumber'])

/** True when this module renders the per-stage strip and the sticky panel. */
export function isStageScopedModule(module: string): boolean {
  return spec.modules.includes(module)
}

/** Where a per-stage value lives on the record. */
export function stageScopedKey(apiName: string, stage: number): string {
  return `${apiName}__s${stage}`
}

/** The carry-forward fields of a module, in the order the spec lists them. */
export function carryForwardFieldsOf(module: string): FieldSpec[] {
  if (!isStageScopedModule(module)) return []
  const byName = new Map(fieldsOf(module).map((f) => [f.api_name, f]))
  return spec.carry_forward.fields
    .map((entry) => byName.get(entry.api_name))
    .filter((f): f is FieldSpec => Boolean(f))
}

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
 */
export function isStageScoped(module: string, field: FieldSpec): boolean {
  if (!isStageScopedModule(module)) return false
  if (spec.carry_forward.fields.some((f) => f.api_name === field.api_name)) return true
  if ((spec.sticky.extra ?? []).some((e) => e.api_name === field.api_name)) return true
  return (
    spec.sticky.sections.includes(field.section) &&
    !DERIVED.has(field.type) &&
    (!spec.sticky.require_condition || Boolean(field.visibility_condition))
  )
}

/** Every api_name this module renders per stage rather than in a section. */
export function stageScopedNamesOf(module: string): Set<string> {
  return new Set(fieldsOf(module).filter((f) => isStageScoped(module, f)).map((f) => f.api_name))
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
 * correcting history, and history must not become the record's current
 * probability.
 */
export function stageScopedPatch(
  field: FieldSpec,
  stage: number,
  currentStage: number,
  value: unknown
): Values {
  const patch: Values = { [stageScopedKey(field.api_name, stage)]: value }
  const carried = spec.carry_forward.fields.some((f) => f.api_name === field.api_name)
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

/**
 * What a LIST row should show for a carry-forward field.
 *
 * Progression % stopped being computed when it was made editable, so a record
 * nobody has typed a number into stores nothing under it — and the kanban card
 * and list column that used to always have a value would read a bare dash. The
 * field's `default_by` resolver is consulted as the fallback, which is the same
 * positional number those screens showed before, now labelled as a suggestion
 * rather than an answer.
 */
export function carriedListValue(module: string, apiName: string, row: Values): unknown {
  if (!isEmpty(row[apiName])) return row[apiName]

  const entry = spec.carry_forward.fields.find((f) => f.api_name === apiName)
  if (!entry) return row[apiName]

  const stages = Object.keys(row)
    .filter((k) => k.startsWith(`${apiName}__s`) && !isEmpty(row[k]))
    .map((k) => Number(k.slice(`${apiName}__s`.length)))
    .filter((n) => Number.isInteger(n))
    .sort((a, b) => b - a)
  if (stages.length) return row[stageScopedKey(apiName, stages[0])]

  const resolve = resolverFor(entry.default_by)
  return resolve ? resolve(module, row) : undefined
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
 * union of three things that are asked in three different places — inline
 * beside the status, in the metrics strip, in the transition dialog — because
 * the point of the panel is that the RECORD's answers are all in one place
 * even though its QUESTIONS are not.
 */
export function reasonFieldsOf(module: string): FieldSpec[] {
  const scoped = stageScopedNamesOf(module)
  const history = historyOnlyNamesOf(module)
  const carried = new Set(spec.carry_forward.fields.map((f) => f.api_name))
  return fieldsOf(module).filter(
    (f) => (scoped.has(f.api_name) && !carried.has(f.api_name)) || history.has(f.api_name)
  )
}

/**
 * Stage-scoped fields this module draws INLINE, next to the field that asks
 * for them — see lib/spec/anchors.ts.
 *
 * These must NOT be added to a form's hiddenFields: they are rendered by the
 * form itself now, which is the entire point of anchoring them. The ones that
 * are not anchored (the two metrics, the probability justification) still are
 * hidden, because a surface of their own draws them.
 */
export function inlineStageScopedNamesOf(module: string): Set<string> {
  return new Set(
    fieldsOf(module)
      .filter((f) => isStageScoped(module, f) && Boolean(f.anchor_field))
      .map((f) => f.api_name)
  )
}

/**
 * What a pipeline form must not draw, because another surface draws it.
 *
 * The stage-scoped names MINUS the anchored ones, PLUS the transition-written
 * ones. Before anchors this was simply stageScopedNamesOf(); the subtraction is
 * A2 and the addition is A3.
 */
export function hiddenFromFormNamesOf(module: string): Set<string> {
  const inline = inlineStageScopedNamesOf(module)
  const hidden = new Set([...stageScopedNamesOf(module)].filter((n) => !inline.has(n)))
  for (const name of historyOnlyNamesOf(module)) hidden.add(name)
  return hidden
}
