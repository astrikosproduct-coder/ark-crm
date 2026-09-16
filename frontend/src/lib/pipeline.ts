import stagesData from '../../spec/stages.json'
import criteriaData from '../../spec/criteria.json'
import gatesData from '../../spec/gates.json'

import { fieldsOf, moduleForStage, optionsFor, rangeOf, stageFieldOf } from '@/lib/spec'

export interface Stage {
  stage: number
  name: string
  /** THE source of the pair a record takes on entering this stage. Whole
   * percents, multiples of 5 — see backend app/progression.py. */
  progression_pct: number | null
  probability_pct: number | null
  owner_role: string
  bid_phase: string | null
  applies_to: 'lead' | 'deal'
}

export interface Criterion {
  stage: number
  type: 'entry' | 'exit'
  code: string
  text: string
  evaluation: 'automatic' | 'attestation' | 'gate' | 'manual' | 'semi_auto'
  source: string | null
  enforcement: 'blocking' | 'advisory'
  playbook_ref: string
}

export interface GateItem {
  code: string
  text: string
  is_critical: boolean
  evaluation: 'automatic' | 'manual' | 'semi_auto' | 'signature'
  source: string | null
}

export interface Gate {
  gate_type: string
  name: string
  anchor_stage: number
  blocking_threshold: number
  enforcement: 'blocking' | 'advisory'
  passes_on: string
  approver_role: string | null
  playbook_ref: string
  warning: string
  items: GateItem[]
}

export const STAGES = stagesData as unknown as Stage[]
export const CRITERIA = criteriaData as unknown as Criterion[]
export const GATES = gatesData as unknown as Gate[]

/**
 * The stages one pipeline module owns, in order.
 *
 * Derived from the range in spec/module_split.json and the stage list in
 * spec/stages.json — NEVER from a picklist and never from `applies_to`. That is
 * deliberate, and it closes two register problems at once instead of hiding
 * them behind sidecar entries:
 *
 *   - `applies_to` in stages.json still says stages 4-7 are `lead`. It is wrong
 *     as of the split and nothing reads it any more.
 *   - `leads_stage` still carries 4_RFP_RFI..7_CLOSE, four keys a Lead can no
 *     longer reach.
 * *
 * Both are raised as register corrections on the Spec Health page. None of
 * them is worked around here.
 */
export function stagesFor(module: string): Stage[] {
  const range = rangeOf(module)
  if (!range) return []
  return STAGES.filter((s) => s.stage >= range[0] && s.stage <= range[1]).sort(
    (a, b) => a.stage - b.stage
  )
}

// Re-exported so a pipeline caller has one import for stages and ranges.
export { moduleForStage, rangeOf, stageFieldOf }

export function stageOf(stage: number | null | undefined): Stage | undefined {
  if (stage === null || stage === undefined) return undefined
  return STAGES.find((s) => s.stage === stage)
}

/** "Stage 3 — Prescription", named by the stages table. Empty when unknown. */
export function stageLabel(stage: number | null | undefined): string {
  const found = stageOf(stage)
  return found ? `Stage ${found.stage} — ${found.name}` : ''
}

/**
 * Progression % / Probability % and their override state. A conversion never
 * blind-copies these: the new record takes its OWN stage's pair on create
 * (app/progression.py), and copying the source's numbers or override would
 * claim a decision the new record never made. See LeadAdvanceDialog.tsx and
 * opportunities/ConvertToDealDialog.tsx.
 */
export const STAGE_PCT_FIELDS: ReadonlySet<string> = new Set([
  'progression_pct',
  'probability_pct',
  'progression_default_pct',
  'probability_default_pct',
  'is_overridden',
  'overridden_by',
  'overridden_date',
])

/** 409 ALREADY_CONVERTED — backend/app/conversion.py. */
export interface AlreadyConverted {
  message: string
  target_module: string | null
  target_id: string | null
}

/**
 * The record this one already became, when a conversion was refused for that
 * reason — so a dialog can send the user to it instead of offering Confirm
 * again. Null for every other failure.
 */
export function alreadyConvertedOf(error: unknown): AlreadyConverted | null {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (detail && typeof detail === 'object' && (detail as { code?: unknown }).code === 'ALREADY_CONVERTED') {
    return detail as AlreadyConverted
  }
  return null
}

/**
 * leads.project_stage is a picklist keyed like "3_PRESCRIPTION" (see
 * spec/picklists.json leads_stage), but a transition and the readiness engine
 * both need the plain leading integer. Accepts a number too, since a record
 * fresh off create() has not always round-tripped through the picklist coercion
 * — see resolvePicklistValue in lib/spec/index.ts, which the seed loader uses.
 */
export function stageNumberOf(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value !== 'string') return null
  const m = /^(\d+)/.exec(value)
  return m ? Number(m[1]) : null
}

export function currentStageOf(record: Record<string, unknown> | undefined): number | null {
  return stageNumberOf(record?.project_stage)
}

/** The leads_stage picklist key for a stage number — the inverse of stageNumberOf. */
export function stageKeyOf(stage: number): string | undefined {
  return optionsFor('leads_stage').find((o) => stageNumberOf(o.key) === stage)?.key
}

/** Deal-side equivalent of currentStageOf — reads deals.deal_stage instead of project_stage. */
export function currentDealStageOf(record: Record<string, unknown> | undefined): number | null {
  return stageNumberOf(record?.deal_stage)
}

/**
 * The deals__deal_stage picklist key for a Deal stage — the inverse of
 * currentDealStageOf. 7_CLOSE exists since 0022, where a paid POC/Pilot Deal
 * sits; ordinary conversions still open a Deal at Stage 8.
 */
export function dealStageKeyOf(stage: number): string | undefined {
  return optionsFor('deals__deal_stage').find((o) => stageNumberOf(o.key) === stage)?.key
}

/** The section of `module` that carries a stage's fields — STAGE 3 — PRESCRIPTION,
 * for example — read off the register rather than hardcoded, so a resectioned
 * register still lines up with the rail.
 *
 * SINGULAR — returns only the first section it finds. Kept for the create
 * pages, which open a record at one fixed stage that has always had exactly
 * one section. A detail page's "current stage" tab must use sectionsForStage
 * instead: Deals' Stage 7 has TWO — "STAGE 7 — COMMERCIAL TERMS" and
 * "STAGE 7 — CLOSE" — and Opportunities' Stage 4 has three, so this function
 * would silently show one and drop the rest. */
export function sectionForStage(module: string, stage: number): string | undefined {
  return fieldsOf(module).find((f) => f.capture_stage === stage)?.section
}

/**
 * Every section of `module` that carries this stage's fields, in the
 * module's own order — plural counterpart to sectionForStage, for a screen
 * that must not silently drop a second section sharing a stage number.
 *
 * A stage with more than one section is how the register groups a big stage:
 * Deals' Stage 7 splits what was won (fixed) from the closing work, and
 * Opportunities' Stage 4 splits the RFP from revenue and from cost & margin.
 * All are real; a screen showing only the first would make the others' fields
 * unreachable, not merely miscategorised.
 */
export function sectionsForStage(module: string, stage: number): string[] {
  const seen: string[] = []
  for (const f of fieldsOf(module)) {
    if (f.capture_stage === stage && !seen.includes(f.section)) seen.push(f.section)
  }
  return seen
}

export function criteriaFor(stage: number, type: 'entry' | 'exit'): Criterion[] {
  return CRITERIA.filter((c) => c.stage === stage && c.type === type)
}

export function gateForAnchor(stage: number): Gate | undefined {
  return GATES.find((g) => g.anchor_stage === stage)
}

export function gateOfType(gateType: string | null | undefined): Gate | undefined {
  if (!gateType) return undefined
  return GATES.find((g) => g.gate_type === gateType)
}

/**
 * The actor stamped on SEED-DERIVED rows only — not the signed-in user.
 *
 * This used to be `CURRENT_USER_ID`, read from 39 places as the identity of
 * whoever was using the application. It is not that any more: real identity
 * comes from Microsoft Entra via `currentUserId()` in @/lib/currentUser. The
 * one remaining caller is lib/spec/pipelineSeed.ts, which runs at seed time
 * before anybody has signed in and therefore has no real actor to name.
 *
 * Renamed deliberately, so nothing imports it again believing it means "me".
 */
export const SEED_ACTOR_ID = 'USR-001'

/**
 * Stages a transition jumped clean over — evidence of an actual skip, as
 * opposed to a stage merely lacking a transition record because the lead was
 * seeded there directly. Only the first case should ever paint a rail node as
 * skipped: absence of history is not evidence of a skip.
 */
export function skippedStagesOf(transitions: { from: number; to: number }[]): Set<number> {
  // Every stage the record has actually been AT: the one each move landed on,
  // plus the one the earliest move started from, which is where it was created.
  const visited = new Set<number>()
  for (const t of transitions) visited.add(t.to)
  if (transitions.length > 0) visited.add(Math.min(...transitions.map((t) => t.from)))

  const out = new Set<number>()
  for (const t of transitions) {
    if (t.to <= t.from + 1) continue
    // A jump over a stage the record has ALREADY BEEN THROUGH is not a stage
    // it missed. OPP-00003 went 4 -> 5, came back 5 -> 4, then skipped 4 -> 6:
    // Stage 5 was worked and saved, so the rail drew a warning over completed
    // work. The skip is still recorded as a skip on the History timeline —
    // this set only decides what the rail warns about.
    for (let s = t.from + 1; s < t.to; s++) if (!visited.has(s)) out.add(s)
  }
  return out
}

export interface Transition {
  id?: string
  /** The pipeline module the moved record belongs to. */
  module: 'leads' | 'opportunities' | 'deals'
  record_id: string
  from: number
  to: number
  reason: string | null
  is_skip: boolean
  is_reversal: boolean
  /** Criterion codes a person ticked in the Update Stage dialog. */
  attested?: string[]
  /** Always present on a row READ back. Never sent — see NewTransition. */
  actor: string
  timestamp: string
}

/**
 * What a client may POST to /transitions.
 *
 * `actor` and `timestamp` are absent, and that is the whole point: the server
 * takes both from the Entra session and its own clock and ignores anything the
 * body claims (app/routers/transitions.py). This is the table a manager reads
 * to find out who skipped a gate, and a trail whose caller names the person
 * and the moment records a claim rather than an event.
 *
 * Typed as an Omit rather than written out again so the two cannot drift.
 */
export type NewTransition = Omit<Transition, 'id' | 'actor' | 'timestamp'>
