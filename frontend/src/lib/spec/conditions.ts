import { apiNamesOf, fieldOf, isAmbiguous, sectionsDefining, toPicklistKey } from './index'
import { evaluateBool, FUNCTION_NAMES, type EvalScope } from './evaluate'
import { identifiersOf, parse, SpecExprError, type Node } from './parser'
import type { FieldSpec } from '@/types/field'

export type Values = Record<string, unknown>

interface Compiled {
  ast: Node
  deps: string[]
  expr: string
}

const cache = new Map<string, Compiled>()

/**
 * Values the SERVER stamps on a record without the register placing them, each
 * keyed to the register field it belongs to: the stage's own Progression % and
 * Probability % (app/progression.py, PCT_OUT). A condition may read one on any
 * module that places its field.
 *
 * They exist for one rule the register could not otherwise state: Override
 * Justification is asked for when a number DIFFERS FROM WHAT THE STAGE SET.
 * Without these the condition would not compile, a broken condition fails open,
 * and the box showed on every record whether anything was overridden or not.
 * No form draws them and no payload may set them — the server owns both.
 */
const SERVER_STAMPED: Record<string, string> = {
  progression_default_pct: 'progression_pct',
  probability_default_pct: 'probability_pct',
}

/**
 * Parse an expression and check every identifier against the module's api_name
 * set. A typo in the register or the sidecar throws here, naming both the
 * expression and the identifier, rather than evaluating to undefined and
 * quietly hiding a field from a form.
 *
 * An identifier that names a DUPLICATED api_name throws too. An expression is
 * evaluated against a record, and a record keys on api_name alone, so there is
 * no value the identifier could honestly resolve to — binding it to whichever
 * definition the register wrote last would give a plausible wrong answer, which
 * is the one outcome this prototype exists to prevent.
 */
export function compileFor(module: string, expr: string): Compiled {
  const key = `${module}::${expr}`
  const hit = cache.get(key)
  if (hit) return hit

  const ast = parse(expr)
  const deps = identifiersOf(ast)
  const known = apiNamesOf(module)

  for (const name of deps) {
    if (FUNCTION_NAMES.includes(name)) continue

    const stampedFor = SERVER_STAMPED[name]
    if (!known.has(name) && !(stampedFor && known.has(stampedFor))) {
      throw new SpecExprError(
        `Unknown identifier ${JSON.stringify(name)} for module ${JSON.stringify(module)}`,
        expr,
        name
      )
    }

    if (isAmbiguous(module, name)) {
      const where = sectionsDefining(module, name)
        .map((s) => JSON.stringify(s))
        .join(' and ')
      throw new SpecExprError(
        `Ambiguous identifier ${JSON.stringify(name)} for module ${JSON.stringify(module)}: ` +
          `defined in ${where}. A record keys on api_name alone, so this cannot be resolved — ` +
          `the register must rename one of the two.`,
        expr,
        name
      )
    }
  }

  const compiled = { ast, deps, expr }
  cache.set(key, compiled)
  return compiled
}

/**
 * Scope over a record's values. Comparisons against picklist-backed fields are
 * normalised so that a register condition written against a label
 * (`deal_source == 'Partner-sourced'`) matches a control that stores a key.
 */
export function scopeOver(module: string, values: Values, children?: Record<string, Values[]>): EvalScope {
  return {
    get: (name) => values[name] ?? null,
    child: (name) => (children?.[name] ?? []) as Record<string, unknown>[],
    normalise: (identName, stored, literal) => {
      const field = fieldOf(module, identName)
      if (!field || (field.type !== 'picklist' && field.type !== 'multiselect')) {
        return [stored, literal]
      }
      const key = field.picklist
      if (Array.isArray(stored)) {
        return [stored.map((v) => toPicklistKey(key, v)), toPicklistKey(key, literal)]
      }
      return [toPicklistKey(key, stored), toPicklistKey(key, literal)]
    },
  }
}

// ------------------------------------------------------------- visibility

const broken = new Set<string>()

/**
 * Compile, or report and give up. An expression that does not compile is a bug
 * in the register, not in the record being edited, so it must not take the
 * form down. validateSpecExpressions() reports the same failures on startup and
 * on the Spec Health page.
 */
function tryCompile(module: string, expr: string): Compiled | null {
  try {
    return compileFor(module, expr)
  } catch (error) {
    const key = `${module}::${expr}`
    if (!broken.has(key)) {
      broken.add(key)
      console.error('[spec] expression will not compile, ignoring it', error)
    }
    return null
  }
}

/**
 * A field with no visibility_condition is always visible. Everything else is
 * driven by the register.
 *
 * A condition that will not compile fails *open*. Hiding a field because the
 * rule behind it is broken is the one outcome nobody would notice, and this
 * prototype exists to make gaps noticeable.
 */
export function isVisible(field: FieldSpec, values: Values): boolean {
  if (!field.visibility_condition) return true
  const compiled = tryCompile(field.module, field.visibility_condition)
  if (!compiled) return true
  return evaluateBool(compiled.ast, scopeOver(field.module, values), compiled.expr)
}

// ------------------------------------------------------------- requirement

export interface RequirementState {
  required: boolean
  /** Conditional in the register, but the register states no condition. */
  unruled?: boolean
}

/**
 * Whether a field is required *right now*, ignoring stage. Stage-gated
 * mandatory fields are handled by validateForTransition in validation.ts.
 *
 * `condition` is empty in all 572 rows of the register, so every Conditional
 * field without a visibility_condition to stand in for one lands in `unruled`
 * and is treated as optional. Inferring a rule from the field name would put a
 * fabricated business rule in front of BD, which is worse than a missing one.
 */
export function requirementOf(field: FieldSpec, values: Values): RequirementState {
  if (!isVisible(field, values)) return { required: false }

  // A phase1_locked field is disabled — nobody can type a value into it — so
  // the register's Mandatory can no longer be demanded of the user without
  // making the stage it blocks_transition on permanently unreachable. See
  // LockedField in FieldControl.tsx and phase1_locked in types/field.ts.
  if (field.phase1_locked) return { required: false }

  switch (field.requirement) {
    case 'Mandatory':
      return { required: true }

    case 'Conditional': {
      if (!field.condition) return { required: false, unruled: true }
      const compiled = tryCompile(field.module, field.condition)
      // A condition that will not compile states no usable rule, so the field
      // lands with the other unruled ones rather than being demanded.
      if (!compiled) return { required: false, unruled: true }
      return evaluateBool(compiled.ast, scopeOver(field.module, values), compiled.expr)
        ? { required: true }
        : { required: false }
    }

    default:
      // System, Computed, Advisory, Optional are never demanded of the user.
      return { required: false }
  }
}

// ----------------------------------------------------------- lookup filters

const filterCache = new Map<string, Node>()

/**
 * Lookup filters run against rows of the target collection, which are seed
 * records rather than spec fields, so identifiers cannot be validated and
 * string comparison is slug-normalised — the seed mixes labels
 * (accounts.account_types) with keys (users.roles).
 */
export function matchesLookupFilter(record: Record<string, unknown>, expr: string): boolean {
  let ast = filterCache.get(expr)
  if (!ast) {
    ast = parse(expr)
    filterCache.set(expr, ast)
  }
  return evaluateBool(ast, { get: (name) => record[name] ?? null, compare: 'slug' }, expr)
}

export function applyLookupFilter(
  records: Record<string, unknown>[],
  expr: string | undefined
): Record<string, unknown>[] {
  if (!expr) return records
  return records.filter((r) => matchesLookupFilter(r, expr))
}
