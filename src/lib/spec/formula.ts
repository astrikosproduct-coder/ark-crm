import { compileFor, scopeOver, type Values } from './conditions'
import { evaluate } from './evaluate'
import { planFor } from './graph'
import { fields, fieldsOf, isAmbiguous, sectionsDefining } from './index'
import { parse, SpecExprError } from './parser'
import { resolverFor } from './resolvers'
import type { FieldSpec } from '@/types/field'

export type Children = Record<string, Values[]>

/**
 * Evaluate every computed field of a module in dependency order and return
 * them as a patch. Nothing is written to the record here — computed values are
 * derived at render and only snapshotted when the form is saved, so a change
 * to a formula in the sidecar takes effect on existing records immediately.
 */
export function computeAll(module: string, values: Values, children?: Children): Values {
  const { order } = planFor(module)

  // Each field is evaluated against the values computed so far, which is what
  // makes a computed-on-computed chain resolve in one pass.
  const working: Values = { ...values }
  const out: Values = {}

  // Named resolvers run FIRST, so an ordinary computed_expr may read one of
  // them by api_name. They take no dependency on another computed field —
  // progression_pct reads the record's stage, which is a plain stored value —
  // so they need no ordering among themselves.
  for (const field of fieldsOf(module)) {
    if (!field.computed_by) continue
    const resolve = resolverFor(field.computed_by)
    if (!resolve) {
      // Reported on Spec Health. The field reads blank rather than the module
      // losing its other computed values to one unknown name.
      console.error(
        `[spec] ${field.qref} names computed_by ${JSON.stringify(field.computed_by)}, which is not a resolver`
      )
      continue
    }
    try {
      const result = resolve(module, working)
      working[field.api_name] = result
      out[field.api_name] = result
    } catch (error) {
      console.error(`[spec] computed_by "${field.computed_by}" failed for ${field.qref}`, error)
      working[field.api_name] = null
      out[field.api_name] = null
    }
  }

  if (!order.length) return out

  for (const node of order) {
    const { ast } = compileFor(module, node.expr)
    let result: unknown
    try {
      result = evaluate(ast, scopeOver(module, working, children), node.expr)
    } catch (error) {
      // A formula that throws must not take the whole form down with it. The
      // field reads blank and the reason reaches the console.
      console.error(`[spec] computed_expr failed for ${node.field.qref}`, error)
      result = null
    }
    working[node.field.api_name] = result
    out[node.field.api_name] = result
  }

  return out
}

/** Merge a record's stored values with freshly computed ones. */
export function withComputed(module: string, values: Values, children?: Children): Values {
  return { ...values, ...computeAll(module, values, children) }
}

/**
 * Why a computed field has no value to show. Used by the control to say
 * something honest instead of rendering an empty box.
 */
export function computedGap(field: FieldSpec): string | null {
  if (field.type !== 'computed') return null
  if (field.computed_expr) return null
  if (field.computed_by) {
    return resolverFor(field.computed_by)
      ? null
      : `computed_by names "${field.computed_by}", which is not a resolver in lib/spec/resolvers.ts.`
  }
  if (field.unexpressed) return field.unexpressed
  return 'No formula in the field register for this field.'
}

// ------------------------------------------------------- startup validation

export interface SpecProblem {
  /** Fully qualified — module.section.api_name — so a duplicate is identifiable. */
  ref: string
  kind:
    | 'computed_expr'
    | 'visibility_condition'
    | 'condition'
    | 'lookup_filter_expr'
    | 'cycle'
    | 'ambiguous_target'
  expr: string
  message: string
}

/**
 * Compile every expression in the spec. Called once from main.tsx so a typo in
 * extensions.json fails on startup with the field and the identifier named,
 * instead of surfacing much later as a field that silently never appears.
 */
export function validateSpecExpressions(): SpecProblem[] {
  const problems: SpecProblem[] = []

  const check = (ref: string, module: string, kind: SpecProblem['kind'], expr: string | undefined) => {
    if (!expr) return
    try {
      compileFor(module, expr)
    } catch (error) {
      problems.push({
        ref,
        kind,
        expr,
        message: error instanceof SpecExprError ? error.message : String(error),
      })
    }
  }

  for (const f of fields) {
    // A computed field whose own name is duplicated cannot store its result —
    // see planFor. Reported here so it reaches Spec Health rather than only the
    // console.
    if (f.computed_expr && isAmbiguous(f.module, f.api_name)) {
      problems.push({
        ref: f.qref,
        kind: 'ambiguous_target',
        expr: f.computed_expr,
        message:
          `api_name ${JSON.stringify(f.api_name)} is also defined in ` +
          sectionsDefining(f.module, f.api_name)
            .filter((s) => s !== f.section)
            .map((s) => JSON.stringify(s))
            .join(' and ') +
          '. A record keys on api_name alone, so the two would overwrite each other.',
      })
      continue
    }

    check(f.qref, f.module, 'computed_expr', f.computed_expr)
    check(f.qref, f.module, 'visibility_condition', f.visibility_condition ?? undefined)
    check(f.qref, f.module, 'condition', f.condition ?? undefined)
  }

  // A lookup filter's identifiers name columns on the target collection, not
  // fields of this module, so only its syntax can be checked.
  for (const f of fields) {
    if (!f.lookup_filter_expr) continue
    try {
      parse(f.lookup_filter_expr)
    } catch (error) {
      problems.push({
        ref: f.qref,
        kind: 'lookup_filter_expr',
        expr: f.lookup_filter_expr,
        message: error instanceof SpecExprError ? error.message : String(error),
      })
    }
  }

  const modulesSeen = new Set(fields.map((f) => f.module))
  for (const module of modulesSeen) {
    try {
      planFor(module)
    } catch (error) {
      problems.push({
        ref: module,
        kind: 'cycle',
        expr: '',
        message: error instanceof SpecExprError ? error.message : String(error),
      })
    }
  }

  return problems
}

/** Computed fields of a module, in evaluation order. Useful for debugging. */
export function computedOrder(module: string): string[] {
  return planFor(module).order.map((n) => n.field.api_name)
}
