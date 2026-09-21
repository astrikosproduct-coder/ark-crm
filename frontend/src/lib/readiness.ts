import { fieldOf } from '@/lib/spec'
import { scopeOver, type Values } from '@/lib/spec/conditions'
import { withComputed } from '@/lib/spec/formula'
import { evaluateBool } from '@/lib/spec/evaluate'
import { identifiersOf, parse } from '@/lib/spec/parser'
import {
  criteriaFor,
  gateForAnchor,
  type Criterion,
  type Gate,
} from '@/lib/pipeline'
import type { FieldSpec } from '@/types/field'

export type CheckStatus = 'pass' | 'fail' | 'warn'

/** One field a criterion names, and whether the record has answered it yet. */
export interface ProofField {
  field: FieldSpec
  filled: boolean
}

export interface ReadinessItem {
  key: string
  code?: string
  label: string
  status: CheckStatus
  enforcement?: 'blocking' | 'advisory'
  /**
   * EVERY field the criterion's source names, in the order it names them.
   *
   * Plural on purpose. "budget_estimate && probable_award_date" is one
   * criterion over two fields, and it used to be shown — and linked — as the
   * first alone: fill Budget Estimate, save, and the box stayed unticked
   * because Probable Award Date was still empty, while the link kept sending
   * the user back to the field they had just filled. Every field is listed
   * now, each with its own state.
   */
  proofs: ProofField[]
  /**
   * Where a click on this criterion goes: the first field still to fill that
   * the record can fill AT ITS CURRENT STAGE. Absent when there is no such
   * field — a link into a stage the record has not reached would open that
   * stage's form early, which is the one thing the stage model forbids.
   */
  proof?: FieldSpec
  /**
   * Set when the criterion's fields are asked for at a stage the record has
   * not reached yet — an entry criterion of the stage being entered, usually.
   * Such a criterion cannot be filled in from here, so it becomes a check a
   * person ticks in the Update Stage dialog; the fields themselves are
   * demanded once the record is at this stage (mandatory_from).
   */
  askedAtStage?: number
  /**
   * Ticked. The criterion evaluated true, or — where the register's source is
   * prose that nothing can evaluate — every field it names carries a value.
   *
   * Derived, never stored: there is no separate place to "tick a criterion off"
   * and there must not be, or the record and the checklist could disagree about
   * the same fact. The box is a reading of the record, so the way to tick it is
   * to fill the fields it names.
   */
  checked: boolean
  /**
   * Nothing on the record can tick this one here — its source is prose, an
   * attestation or a signature naming no field, or its fields belong to a later
   * stage — so a PERSON ticks it, in the Update Stage dialog, and a forward move
   * waits until they have. The ticks are kept on the transition
   * (stage_transitions.attested) with who and when.
   */
  manual: boolean
}

export interface ReadinessLayer {
  /** No 'mandatory': layer 1 is not shown in this panel — see computeReadiness. */
  key: 'exit' | 'entry' | 'gate'
  label: string
  items: ReadinessItem[]
}

export interface Readiness {
  from: number
  to: number
  layers: ReadinessLayer[]
}

/** Empty for the purpose of "has this been answered": null, blank, or no rows. */
function isFilled(value: unknown): boolean {
  if (value === null || value === undefined) return false
  if (typeof value === 'string') return value.trim() !== ''
  if (Array.isArray(value)) return value.length > 0
  return true
}

/**
 * Every field of this module that a criterion's source names, once each.
 *
 * Most sources parse — "demo_agreed == true" — and the identifiers come out of
 * the AST. Many do not: the register is full of prose written for a person
 * ("budget_estimate and probable_award_date"), and those still name real
 * fields, so a failed parse falls back to reading identifier-shaped words out
 * of the text. Either way a name has to resolve against the register before it
 * is offered as proof — a word that merely looks like an api_name is not one.
 */
function proofFieldsOf(module: string, source: string | null): FieldSpec[] {
  if (!source || source.startsWith('gate:')) return []

  let names: string[]
  try {
    names = identifiersOf(parse(source))
  } catch {
    names = source.match(/[a-z][a-z0-9_]{2,}/g) ?? []
  }
  const seen = new Set<string>()
  const out: FieldSpec[] = []
  for (const name of names) {
    const field = fieldOf(module, name)
    if (field && !seen.has(field.api_name)) {
      seen.add(field.api_name)
      out.push(field)
    }
  }
  return out
}

/** A field the record can be edited on at the stage it is at. */
function reachableAt(field: FieldSpec, currentStage: number): boolean {
  return field.capture_stage === null || field.capture_stage <= currentStage
}

/**
 * A criterion's `source` is written for a human, not this parser — some rows
 * are valid expressions ("demo_agreed == true"), many are prose ("budget_estimate
 * and probable_award_date", "contact_roles has DECM or RECM"). Anything that
 * fails to parse, or whose evaluation is attestation/manual/signature, cannot
 * be judged here, and says so by staying unticked rather than by fabricating a
 * pass or a fail — the same fail-open posture the rest of the spec engine takes
 * on a broken expression.
 */
function evaluateCriterionLike(
  module: string,
  values: Values,
  source: string | null,
  evaluation: string
): { status: CheckStatus; manual: boolean } {
  // ONE RULE FOR A MANUAL TICK: nothing on this record can answer the
  // criterion. No source, a gate (the Gates module is not built), prose the
  // engine cannot read, or a source naming something this record does not
  // carry — poc.outcome, bid.open_tbe_queries, a field of another module.
  if (!source || source.startsWith('gate:')) return { status: 'warn', manual: true }

  let ast: ReturnType<typeof parse>
  try {
    ast = parse(source)
  } catch {
    return { status: 'warn', manual: true }
  }
  if (identifiersOf(ast).some((name) => !fieldOf(module, name))) return { status: 'warn', manual: true }

  if (evaluation === 'attestation' || evaluation === 'manual' || evaluation === 'signature') {
    return { status: 'warn', manual: false }
  }

  try {
    const result = evaluateBool(ast, scopeOver(module, values, childrenOf(values)), source)
    if (result) return { status: 'pass', manual: false }
    return { status: evaluation === 'automatic' || evaluation === 'semi_auto' ? 'fail' : 'warn', manual: false }
  } catch {
    return { status: 'warn', manual: true }
  }
}

/** A record's child lists, by name, so count() and sum() can read them. */
function childrenOf(values: Values): Record<string, Values[]> {
  const out: Record<string, Values[]> = {}
  for (const [key, value] of Object.entries(values)) if (Array.isArray(value)) out[key] = value as Values[]
  return out
}

function criteriaLayer(
  key: 'exit' | 'entry',
  module: string,
  values: Values,
  stage: number,
  currentStage: number,
  label: string
): ReadinessLayer {
  const items: ReadinessItem[] = criteriaFor(stage, key).map((c) => {
    const { status, manual } = evaluateCriterionLike(module, values, c.source, c.evaluation)
    const proofs: ProofField[] = manual
      ? []
      : proofFieldsOf(module, c.source).map((field) => ({ field, filled: isFilled(values[field.api_name]) }))

    // A criterion nothing can evaluate still has an answer on the record:
    // whether EVERY field it names has been filled in.
    const checked =
      status === 'pass' ? true : status === 'fail' ? false : proofs.length > 0 && proofs.every((p) => p.filled)

    const base = { key: c.code, code: c.code, label: c.text, enforcement: c.enforcement, proofs }

    // Not yet answered, and answered on a stage the record has not reached:
    // Stage 3's entry criteria name Stage 3's fields. Linking to them from
    // Stage 2 opened Stage 3's form on a Stage 2 record. It is a check the
    // person confirms on the move instead, and the fields are asked for there.
    const later = proofs
      .filter((p) => !p.filled && !reachableAt(p.field, currentStage))
      .map((p) => p.field.capture_stage as number)
    if (!checked && later.length > 0) {
      return { ...base, status: 'warn', checked: false, manual: true, askedAtStage: Math.max(...later) }
    }

    const reachable = proofs.filter((p) => reachableAt(p.field, currentStage))
    const proof = (reachable.find((p) => !p.filled) ?? reachable[0])?.field
    return { ...base, status, checked, manual, proof }
  })
  return { key, label, items }
}

/**
 * The gate anchored at the stage being entered, if there is one.
 *
 * A stage with no gate used to render a row saying "No gate anchors this
 * stage" — a line whose entire content is that there is nothing to read. The
 * layer is omitted instead.
 */
function gateLayer(to: number): ReadinessLayer | null {
  const gate = gateForAnchor(to)
  if (!gate) return null
  return {
    key: 'gate',
    label: 'Gate',
    items: [
      {
        key: gate.gate_type,
        code: gate.gate_type,
        label: gate.name,
        status: 'warn',
        enforcement: gate.enforcement,
        proofs: [],
        checked: false,
        // The Gates module is not built, so nothing records a gate's outcome;
        // the person moving the record confirms it.
        manual: true,
      },
    ],
  }
}

/**
 * Layers 2 to 4 of the four-layer transition check from CLAUDE.md: exit
 * criteria of the stage being left, entry criteria of the stage being entered,
 * gate status. `from` is the stage the record is AT — it decides which fields
 * a criterion may send the user to.
 *
 * LAYER 1, MANDATORY FIELDS, IS DELIBERATELY NOT SHOWN HERE. It restated what
 * the form already says — every demanded field carries a red asterisk, an
 * inline error and a count above the Save button. validateForTransition in
 * lib/spec/validation.ts is still the engine for layer 1.
 */
export function computeReadiness(module: string, values: Values, from: number, to: number): Readiness {
  // COMPUTED FIELDS FIRST. A computed field is never stored on any module in
  // this build, so a criterion naming one — X4.1's submitted_on_time, X6.1's
  // total_value_tcv — read an empty value and could never tick itself, however
  // complete the record was. The form works the same formulas out on screen,
  // so the checklist said "not met" beside a field showing Yes.
  const values_ = withComputed(module, values, childrenOf(values))
  const layers = [
    criteriaLayer('exit', module, values_, from, from, 'Exit criteria'),
    criteriaLayer('entry', module, values_, to, from, 'Entry criteria'),
    gateLayer(to),
  ]
  // An empty layer is a heading with nothing under it. Dropped rather than
  // captioned "Nothing to check" — the absence says that already.
  return { from, to, layers: layers.filter((l): l is ReadinessLayer => Boolean(l) && l!.items.length > 0) }
}

/** The checks a person must tick before moving forward, one per code. */
export function attestationsNeeded(module: string, values: Values, from: number, to: number): ReadinessItem[] {
  return allChecksOf(module, values, from, to).filter((item) => item.manual)
}

/**
 * EVERY check the dialog draws, one per code — manual and record-read alike.
 *
 * A person may tick a criterion the record says is not met (decided 16 Sep
 * 2026): the record is one reading of a fact and the person moving the stage
 * is another, and the four-layer check is advisory here. Such a tick is a
 * CLAIM, so it is recorded on the transition beside the manual ones, with who
 * and when — which is what this list exists to collect. It does not change
 * what blocks the move: only manual checks do that, as before.
 */
export function allChecksOf(module: string, values: Values, from: number, to: number): ReadinessItem[] {
  const seen = new Map<string, ReadinessItem>()
  for (const layer of computeReadiness(module, values, from, to).layers) {
    for (const item of layer.items) if (!seen.has(item.key)) seen.set(item.key, item)
  }
  return [...seen.values()]
}

export type { Criterion, Gate }
