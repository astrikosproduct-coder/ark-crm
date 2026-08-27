import { compileFor } from './conditions'
import { fieldsOf, isAmbiguous, sectionsDefining } from './index'
import { SpecExprError } from './parser'
import type { FieldSpec } from '@/types/field'

export interface ComputedNode {
  field: FieldSpec
  expr: string
  /** api_names in the same module that this field reads. */
  deps: string[]
}

export interface ComputedPlan {
  /** Evaluation order. A field never appears before something it reads. */
  order: ComputedNode[]
  /** api_name -> computed fields that must be recalculated when it changes. */
  dependents: Map<string, string[]>
}

const plans = new Map<string, ComputedPlan>()

/**
 * Order the computed fields of a module so each one is evaluated after
 * everything it reads. leads.third_party_pct_of_tcv divides by
 * leads.total_value_tcv, which is itself computed, so a naive single pass in
 * register order would read a stale value on the first render.
 *
 * Kahn's algorithm, because it reports the cycle rather than blowing the
 * stack.
 */
export function planFor(module: string): ComputedPlan {
  const hit = plans.get(module)
  if (hit) return hit

  const nodes: ComputedNode[] = []
  const own = new Set(fieldsOf(module).map((f) => f.api_name))

  for (const field of fieldsOf(module)) {
    if (!field.computed_expr) continue

    // A computed field whose own api_name is duplicated has nowhere to put its
    // result: computeAll writes into a record keyed on api_name, so the two
    // definitions would overwrite each other. Dropped from the plan and
    // reported, rather than silently producing one field's value under the
    // other field's name.
    if (isAmbiguous(module, field.api_name)) {
      console.error(
        `[spec] computed field ${field.qref} shares its api_name with ${sectionsDefining(
          module,
          field.api_name
        ).join(' and ')} — dropped from the computed plan`
      )
      continue
    }

    let deps: string[]
    try {
      deps = compileFor(module, field.computed_expr).deps
    } catch (error) {
      // Reported by validateSpecExpressions() and on the Spec Health page. The
      // field is dropped from the plan so it reads blank, rather than the whole
      // module losing its computed values to one bad expression.
      console.error(`[spec] computed_expr will not compile for ${field.qref}`, error)
      continue
    }
    nodes.push({
      field,
      expr: field.computed_expr,
      deps: deps.filter((d) => own.has(d)),
    })
  }

  const byName = new Map(nodes.map((n) => [n.field.api_name, n]))
  const indegree = new Map<string, number>()
  const edges = new Map<string, string[]>()

  for (const n of nodes) {
    indegree.set(n.field.api_name, 0)
  }
  for (const n of nodes) {
    for (const dep of n.deps) {
      // Only edges between computed fields matter for ordering; a dependency
      // on a plain input field is already available before any pass runs.
      if (!byName.has(dep)) continue
      edges.set(dep, [...(edges.get(dep) ?? []), n.field.api_name])
      indegree.set(n.field.api_name, (indegree.get(n.field.api_name) ?? 0) + 1)
    }
  }

  const queue = [...indegree.entries()].filter(([, d]) => d === 0).map(([name]) => name)
  const order: ComputedNode[] = []

  while (queue.length) {
    const name = queue.shift() as string
    const node = byName.get(name)
    if (node) order.push(node)
    for (const next of edges.get(name) ?? []) {
      const d = (indegree.get(next) ?? 0) - 1
      indegree.set(next, d)
      if (d === 0) queue.push(next)
    }
  }

  if (order.length !== nodes.length) {
    const stuck = nodes.filter((n) => !order.includes(n)).map((n) => n.field.api_name)
    throw new SpecExprError(
      `Circular computed_expr in module ${JSON.stringify(module)}: ${stuck.join(' -> ')}`,
      stuck.map((s) => byName.get(s)?.expr ?? s).join(' | ')
    )
  }

  const dependents = new Map<string, string[]>()
  for (const n of nodes) {
    for (const dep of n.deps) {
      dependents.set(dep, [...(dependents.get(dep) ?? []), n.field.api_name])
    }
  }

  const plan = { order, dependents }
  plans.set(module, plan)
  return plan
}

/** Computed fields that need recalculating when `apiName` changes, transitively. */
export function dependentsOf(module: string, apiName: string): Set<string> {
  const { dependents } = planFor(module)
  const out = new Set<string>()
  const stack = [apiName]

  while (stack.length) {
    const name = stack.pop() as string
    for (const d of dependents.get(name) ?? []) {
      if (out.has(d)) continue
      out.add(d)
      stack.push(d)
    }
  }

  return out
}
