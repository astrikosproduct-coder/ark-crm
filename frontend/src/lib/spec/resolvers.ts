import { daysSinceCompany } from '../time'
import type { Values } from './conditions'

/**
 * Named resolvers for computed fields the expression language cannot express.
 *
 * The language operates over a record's own api_names. Days in the current stage
 * is not a function of any field's VALUE — it reads a derived date and the
 * company clock, neither of which is a field. No expression over api_names can
 * produce it.
 *
 * So the escape hatch is a `computed_by` NAME looked up in the fixed table
 * below: one identifier, resolved against code that was written and reviewed,
 * with no eval() and no Function() anywhere near it — the same containment
 * spec/parser.ts exists to provide. A name with no entry here reads blank and is
 * reported on Spec Health, exactly like a missing computed_expr.
 */

export type SpecResolver = (module: string, values: Values) => unknown

/**
 * Whole days the record has been in the stage it is in now.
 *
 * Reads `stage_entered_date`, which the server derives from the stage_transitions
 * table — the LAST move INTO the current stage, so a pursuit that went 3 -> 5 -> 3
 * is aged from the second Stage 3 and not the first. See app/stage_entry.py.
 *
 * NOT a computed_expr: the expression
 * language operates over a record's own api_names, and stage_entered_date is a
 * derived fact the register has no field for. It is a resolver rather than the
 * server simply sending the number so that ONE clock counts — daysSinceCompany
 * is the same company-calendar count app/clock.py::days_since performs, so the
 * figure here, the figure on a Kanban card and the figure from the API agree by
 * construction rather than by three implementations staying in step.
 *
 * Falls back to created_date: a record that has never transitioned has been in
 * its stage since it was created, which is a real answer and not a placeholder.
 */
function daysInStage(_module: string, values: Values): number | null {
  return daysSinceCompany(values.stage_entered_date ?? values.created_date)
}

/**
 * Whole days since the record last changed.
 *
 * modified_date is a System field the server stamps on every save, so this is
 * expressible from the record alone — but it lives here beside daysInStage
 * rather than as a computed_expr because the expression language has no "now".
 * `days_between(modified_date, TODAY)` would need a TODAY identifier, and one
 * that resolved against the browser's own clock would reintroduce exactly the
 * disagreement lib/time.ts was written to remove.
 *
 * Deals stamp modified_by_date / created_by_date, not modified_date — the
 * Deals sheet names its own system fields, see the Deal docstring in
 * app/models.py — so both spellings are read.
 */
function daysSinceUpdate(_module: string, values: Values): number | null {
  return daysSinceCompany(
    values.modified_date ??
      values.modified_by_date ??
      values.created_date ??
      values.created_by_date
  )
}

const RESOLVERS: Record<string, SpecResolver> = {
  days_in_stage: daysInStage,
  days_since_update: daysSinceUpdate,
}

/** The resolver a field's `computed_by` names, or undefined when there is none. */
export function resolverFor(name: string | undefined): SpecResolver | undefined {
  return name ? RESOLVERS[name] : undefined
}

/** Every resolver name the spec may legally use. Read by Spec Health. */
export const RESOLVER_NAMES = Object.keys(RESOLVERS)
