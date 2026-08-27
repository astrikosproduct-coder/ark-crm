import {
  addDays,
  differenceInBusinessDays,
  differenceInCalendarDays,
  format,
  isValid,
  parseISO,
} from 'date-fns'

import { SpecExprError, type Node } from './parser'

export type Scalar = string | number | boolean | null

export interface EvalScope {
  /** Read an identifier. Return null for absent. */
  get(name: string): unknown
  /**
   * Bring a string literal and a stored value onto common ground before
   * comparison. Used to reconcile picklist keys with picklist labels.
   * Returns the pair unchanged when the field is not picklist-backed.
   */
  normalise?(identName: string, stored: unknown, literal: unknown): [unknown, unknown]
  /** Rows of a child collection, for sum(). */
  child?(name: string): Record<string, unknown>[]
  /** How string equality behaves — see spec/README.md. */
  compare?: 'exact' | 'slug'
}

// ------------------------------------------------------------ value helpers

const ISO_DATE = /^\d{4}-\d{2}-\d{2}([T ]|$)/

export function isBlank(v: unknown): boolean {
  return v === null || v === undefined || v === ''
}

/** Empty is null, not 0 — see the spreadsheet semantics note in spec/README.md. */
export function toNum(v: unknown): number | null {
  if (isBlank(v)) return null
  if (typeof v === 'boolean') return v ? 1 : 0
  const n = typeof v === 'number' ? v : Number(String(v).replace(/,/g, ''))
  return Number.isFinite(n) ? n : null
}

export function toDate(v: unknown): Date | null {
  if (typeof v !== 'string' || !ISO_DATE.test(v)) return null
  const d = parseISO(v)
  return isValid(d) ? d : null
}

function truthy(v: unknown): boolean {
  if (typeof v === 'boolean') return v
  if (isBlank(v)) return false
  if (typeof v === 'number') return v !== 0
  if (Array.isArray(v)) return v.length > 0
  return true
}

/** Case-folded, with -, _ and space treated as equivalent. */
export function slug(v: unknown): string {
  return String(v)
    .toLowerCase()
    .replace(/[\s\-_]+/g, '')
    .trim()
}

function eq(a: unknown, b: unknown, mode: 'exact' | 'slug'): boolean {
  if (isBlank(a) && isBlank(b)) return true
  if (isBlank(a) || isBlank(b)) return false
  if (typeof a === 'boolean' || typeof b === 'boolean') return truthy(a) === truthy(b)

  const na = toNum(a)
  const nb = toNum(b)
  if (na !== null && nb !== null && typeof a !== 'string' && typeof b !== 'string') return na === nb

  return mode === 'slug' ? slug(a) === slug(b) : String(a) === String(b)
}

function relational(op: string, l: unknown, r: unknown): boolean | null {
  if (isBlank(l) || isBlank(r)) return null

  const dl = toDate(l)
  const dr = toDate(r)
  let a: number
  let b: number

  if (dl && dr) {
    a = dl.getTime()
    b = dr.getTime()
  } else {
    const nl = toNum(l)
    const nr = toNum(r)
    if (nl === null || nr === null) {
      const sl = String(l)
      const sr = String(r)
      a = sl < sr ? -1 : sl > sr ? 1 : 0
      b = 0
    } else {
      a = nl
      b = nr
    }
  }

  switch (op) {
    case '<':
      return a < b
    case '<=':
      return a <= b
    case '>':
      return a > b
    case '>=':
      return a >= b
    default:
      return null
  }
}

/**
 * Arithmetic follows a spreadsheet: all-blank operands give blank, so an
 * untouched lead shows an empty Total Value rather than $0. Once any operand
 * is present the blanks count as zero.
 */
function arithmetic(op: string, l: unknown, r: unknown): number | null {
  const a = toNum(l)
  const b = toNum(r)
  if (a === null && b === null) return null

  const x = a ?? 0
  const y = b ?? 0

  switch (op) {
    case '+':
      return x + y
    case '-':
      return x - y
    case '*':
      return x * y
    case '/':
      // Blank rather than Infinity or NaN. A discount % with no list price
      // reads as empty, which is the truth.
      return y === 0 ? null : x / y
    default:
      return null
  }
}

// ----------------------------------------------------------------- builtins

type Fn = (args: unknown[], expr: string) => unknown

const FUNCTIONS: Record<string, Fn> = {
  concat: (args) => args.filter((a) => !isBlank(a)).map((a) => String(a)).join(''),

  coalesce: (args) => args.find((a) => !isBlank(a)) ?? null,

  round: (args) => {
    const n = toNum(args[0])
    if (n === null) return null
    const dp = toNum(args[1]) ?? 0
    const f = 10 ** dp
    return Math.round(n * f) / f
  },

  abs: (args) => {
    const n = toNum(args[0])
    return n === null ? null : Math.abs(n)
  },

  min: (args) => {
    const ns = args.map(toNum).filter((n): n is number => n !== null)
    return ns.length ? Math.min(...ns) : null
  },

  max: (args) => {
    const ns = args.map(toNum).filter((n): n is number => n !== null)
    return ns.length ? Math.max(...ns) : null
  },

  if: (args) => (truthy(args[0]) ? args[1] ?? null : args[2] ?? null),

  add_days: (args) => {
    const d = toDate(args[0])
    const n = toNum(args[1])
    if (!d || n === null) return null
    return format(addDays(d, n), 'yyyy-MM-dd')
  },

  days_between: (args) => {
    const a = toDate(args[0])
    const b = toDate(args[1])
    if (!a || !b) return null
    return differenceInCalendarDays(b, a)
  },

  business_days: (args) => {
    const a = toDate(args[0])
    const b = toDate(args[1])
    if (!a || !b) return null
    return differenceInBusinessDays(b, a)
  },
}

export const FUNCTION_NAMES = [...Object.keys(FUNCTIONS), 'sum']

// ---------------------------------------------------------------- evaluator

export function evaluate(node: Node, scope: EvalScope, expr: string): unknown {
  const mode = scope.compare ?? 'exact'

  const walk = (n: Node): unknown => {
    switch (n.k) {
      case 'num':
        return n.v
      case 'str':
        return n.v
      case 'bool':
        return n.v
      case 'null':
        return null
      case 'ident':
        return scope.get(n.name) ?? null

      case 'unary':
        if (n.op === '!') return !truthy(walk(n.arg))
        {
          const v = toNum(walk(n.arg))
          return v === null ? null : -v
        }

      case 'cond':
        return truthy(walk(n.test)) ? walk(n.a) : walk(n.b)

      case 'call':
        return call(n)

      case 'bin':
        return binary(n)
    }
  }

  function binary(n: Extract<Node, { k: 'bin' }>): unknown {
    if (n.op === '&&') return truthy(walk(n.l)) ? truthy(walk(n.r)) : false
    if (n.op === '||') return truthy(walk(n.l)) ? true : truthy(walk(n.r))

    let l = walk(n.l)
    let r = walk(n.r)

    // Reconcile a stored picklist key with a label written in the register,
    // whichever side of the operator each happens to be on.
    if (scope.normalise) {
      if (n.l.k === 'ident' && n.r.k === 'str') [l, r] = scope.normalise(n.l.name, l, r)
      else if (n.r.k === 'ident' && n.l.k === 'str') [r, l] = scope.normalise(n.r.name, r, l)
    }

    switch (n.op) {
      case '==':
        return eq(l, r, mode)
      case '!=':
        return !eq(l, r, mode)
      case '<':
      case '<=':
      case '>':
      case '>=':
        return relational(n.op, l, r)
      case 'includes': {
        if (Array.isArray(l)) return l.some((item) => eq(item, r, mode))
        if (isBlank(l)) return false
        return mode === 'slug'
          ? slug(l).includes(slug(r))
          : String(l).includes(String(r))
      }
      default:
        return arithmetic(n.op, l, r)
    }
  }

  function call(n: Extract<Node, { k: 'call' }>): unknown {
    // sum(child, field, filter?) is the one function whose arguments are names
    // and a row-scoped predicate rather than values, so it is evaluated by
    // hand instead of through the argument list.
    if (n.name === 'sum') {
      const [childArg, fieldArg, filterArg] = n.args
      if (childArg?.k !== 'ident' || fieldArg?.k !== 'ident') {
        throw new SpecExprError('sum() takes a child name and a column name', expr)
      }
      const rows = scope.child?.(childArg.name) ?? []
      let total: number | null = null

      for (const row of rows) {
        if (filterArg) {
          const rowScope: EvalScope = {
            get: (name) => row[name] ?? null,
            compare: mode,
            // Child columns are spec fields of the same module — a quote line's
            // line_charge_type is a quotes field — so the row scope needs the
            // same picklist reconciliation as the parent, or a filter written
            // against a label never matches a stored key.
            normalise: scope.normalise,
          }
          if (!truthy(evaluate(filterArg, rowScope, expr))) continue
        }
        const v = toNum(row[fieldArg.name])
        if (v !== null) total = (total ?? 0) + v
      }

      return total
    }

    const fn = FUNCTIONS[n.name]
    if (!fn) throw new SpecExprError(`Unknown function ${JSON.stringify(n.name)}`, expr)
    return fn(n.args.map(walk), expr)
  }

  return walk(node)
}

export function evaluateBool(node: Node, scope: EvalScope, expr: string): boolean {
  return truthy(evaluate(node, scope, expr))
}
