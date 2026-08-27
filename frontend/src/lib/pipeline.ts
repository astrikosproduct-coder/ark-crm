import stagesData from '../../spec/stages.json'
import criteriaData from '../../spec/criteria.json'
import gatesData from '../../spec/gates.json'

import { fieldsOf, moduleForStage, optionsFor, rangeOf, stageFieldOf } from '@/lib/spec'

export interface Stage {
  stage: number
  name: string
  prob_min: number | null
  prob_max: number | null
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
 * deliberate, and it closes three register problems at once instead of hiding
 * them behind sidecar entries:
 *
 *   - `applies_to` in stages.json still says stages 4-7 are `lead`. It is wrong
 *     as of the split and nothing reads it any more.
 *   - `leads_stage` still carries 4_RFP_RFI..7_CLOSE, four keys a Lead can no
 *     longer reach.
 *   - `deals__deal_stage` has no 7_CLOSE at all, so a Deal opening at Stage 7
 *     would have no value to store.
 *
 * All three are raised as register corrections on the Spec Health page. None of
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

/** The band midpoint a transition writes into probability_pct. Rounded — the
 * field is a plain number, not a computed one, so nothing re-derives it. */
export function probabilityMidpoint(stage: number): number | null {
  const s = stageOf(stage)
  if (!s || s.prob_min === null || s.prob_max === null) return null
  return Math.round((s.prob_min + s.prob_max) / 2)
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
 * currentDealStageOf.
 *
 * The Deals picklist intentionally starts at Project Success. Stage 7 / Close
 * is the conversion boundary and is not a Deal Stage option.
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
 * instead: Deals' Stage 7 has TWO — its own register-native "ON CONVERSION"
 * plus "STAGE 7 — CLOSE", moved in from Leads by the pipeline split — and this
 * function would silently show one and drop the other. */
export function sectionForStage(module: string, stage: number): string | undefined {
  return fieldsOf(module).find((f) => f.capture_stage === stage)?.section
}

/**
 * Every section of `module` that carries this stage's fields, in the
 * module's own order — plural counterpart to sectionForStage, for a screen
 * that must not silently drop a second section sharing a stage number.
 *
 * A stage having more than one section is not a design goal, it is what
 * happens when a moved-in section (STAGE 7 — CLOSE, reassigned onto Deals by
 * spec/module_split.json) lands on the same stage number as a section the
 * target module already declared for itself (ON CONVERSION). Both are real;
 * a screen showing only the first would make the second's fields
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
 * No login exists in this prototype. CLAUDE.md is explicit that today the CEO
 * holds every commercial role, so every action in the walkthrough — including
 * a stage transition's actor — is attributed to that one seeded user.
 */
export const CURRENT_USER_ID = 'USR-001'

/**
 * Stages a transition jumped clean over — evidence of an actual skip, as
 * opposed to a stage merely lacking a transition record because the lead was
 * seeded there directly. Only the first case should ever paint a rail node as
 * skipped: absence of history is not evidence of a skip.
 */
export function skippedStagesOf(transitions: { from: number; to: number }[]): Set<number> {
  const out = new Set<number>()
  for (const t of transitions) {
    if (t.to <= t.from + 1) continue
    for (let s = t.from + 1; s < t.to; s++) out.add(s)
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
  actor: string
  timestamp: string
}
