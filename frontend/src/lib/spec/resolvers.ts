import stagesData from '../../../spec/stages.json'
import { stageFieldOf } from './moduleSplit'
import type { Values } from './conditions'

/**
 * Named resolvers for computed fields the expression language cannot express.
 *
 * The language operates over a record's own api_names. progression_pct is not a
 * function of any field's VALUE — it is a function of where the record's stage
 * sits in the ordered list of stages, which is not a field at all. No expression
 * over api_names can produce it.
 *
 * So the escape hatch is a `computed_by` NAME looked up in the fixed table
 * below: one identifier, resolved against code that was written and reviewed,
 * with no eval() and no Function() anywhere near it — the same containment
 * spec/parser.ts exists to provide. A name with no entry here reads blank and is
 * reported on Spec Health, exactly like a missing computed_expr.
 */

interface StageRow {
  stage: number
  name: string
}

const STAGES = stagesData as unknown as StageRow[]

/** Stages in ascending order — the 0-9 spine both pipelines are measured against. */
const ORDERED = [...STAGES].sort((a, b) => a.stage - b.stage)

/**
 * The leading integer of a stage value.
 *
 * project_stage is a picklist keyed "4_RFP_RFI"; deal_stage is keyed
 * "8_PROJECT_SUCCESS"; a record straight off a create can still hold the bare
 * number. All three resolve here. Duplicated from lib/pipeline deliberately:
 * the spec layer must not depend on the pipeline layer, which depends on it.
 */
function stageNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value !== 'string') return null
  const m = /^(\d+)/.exec(value)
  return m ? Number(m[1]) : null
}

/**
 * How far through the whole pursuit this record sits, as a percentage of stage
 * POSITION — 0, 11, 22, 33, 44, 56, 67, 78, 89, 100.
 *
 * Deliberately NOT probability. Probability is a commercial judgement inside the
 * band the register gives each stage; progression is a positional fact. At Stage
 * 7 they read 78% and 90-100%, and a screen showing both is showing two
 * different things on purpose — which is the entire reason this field exists.
 *
 * The divisor is the length of the stage list, never a hardcoded 9: add a Stage
 * 10 to spec/stages.json and every progression re-scales itself.
 *
 * Linear-by-position is this build's choice. The register states no progression
 * curve anywhere, and that is recorded as an open question rather than settled
 * here by picking weights nobody asked for.
 */
function progression(module: string, values: Values): number | null {
  if (ORDERED.length < 2) return null

  const field = stageFieldOf(module)
  if (!field) return null

  const stage = stageNumber(values[field])
  if (stage === null) return null

  const index = ORDERED.findIndex((s) => s.stage === stage)
  if (index === -1) return null

  return Math.round((index / (ORDERED.length - 1)) * 100)
}

export type SpecResolver = (module: string, values: Values) => unknown

const RESOLVERS: Record<string, SpecResolver> = {
  progression,
}

/** The resolver a field's `computed_by` names, or undefined when there is none. */
export function resolverFor(name: string | undefined): SpecResolver | undefined {
  return name ? RESOLVERS[name] : undefined
}

/** Every resolver name the spec may legally use. Read by Spec Health. */
export const RESOLVER_NAMES = Object.keys(RESOLVERS)
