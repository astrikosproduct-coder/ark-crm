import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

import { fieldsOf, listScopeFor, listViewFor } from '@/lib/spec'
import type { FieldSpec, ListScopeOption, ResolvedListScope } from '@/types/field'

/**
 * The Filter panel's state for any live module's list — Zoho's layout (reference
 * shared 17 Sep 2026): tick a field, pick how it compares, give a value, Apply.
 * The record search box stays outside the panel, for speed.
 *
 * The state lives in the URL, under the SAME names the list endpoint takes
 * (backend/app/list_query.py) — `?bd_owner=USR-1&segment_ne=GOVERNMENT&
 * expected_close_month_gte=2026-10-01`. On the pipeline screens the List and
 * Kanban tabs read the one set, so switching tabs keeps it, and a filtered
 * screen can be sent as a link.
 *
 * ONLY THE MODULE'S OWN FIELDS. "Filter by fields" offers what the module's own
 * record carries. Identity an Opportunity or Deal reads through from its Lead
 * is shown on the Related tab, not on the record, so it is offered only where
 * the list view pins it as a Common filter (End Client, owner). A field that is
 * captured at a later stage IS the module's own — Budget Estimate is a Lead
 * field, in the Stage 3 · Prescription section — so each field names its
 * section, and nobody has to wonder where it lives.
 */

export type FilterKind = 'choice' | 'text' | 'date' | 'month' | 'number' | 'checkbox'

export type Operator =
  | 'is'
  | 'isnt'
  | 'contains'
  | 'ncontains'
  | 'starts'
  | 'empty'
  | 'nempty'
  | 'eq'
  | 'lt'
  | 'gt'
  | 'between'
  | 'on'
  | 'before'
  | 'after'

/** One ticked field: how it compares, and to what. `between` holds [from, to]. */
export interface Condition {
  op: Operator
  values: string[]
}

export interface FilterField {
  /** The api_name, which is also the URL key. */
  key: string
  label: string
  kind: FilterKind
  field: FieldSpec
  /** Where the field lives on the record — "Stage 3 · Prescription". */
  section: string
}

export const OPERATORS: Record<FilterKind, Operator[]> = {
  choice: ['is', 'isnt', 'empty', 'nempty'],
  text: ['is', 'isnt', 'contains', 'ncontains', 'starts', 'empty', 'nempty'],
  date: ['on', 'before', 'after', 'between', 'empty', 'nempty'],
  month: ['on', 'before', 'after', 'between', 'empty', 'nempty'],
  number: ['eq', 'lt', 'gt', 'between', 'empty', 'nempty'],
  checkbox: ['is'],
}

export const OPERATOR_LABELS: Record<Operator, string> = {
  is: 'is',
  isnt: 'isn’t',
  contains: 'contains',
  ncontains: 'doesn’t contain',
  starts: 'starts with',
  empty: 'is empty',
  nempty: 'is not empty',
  eq: '=',
  lt: '<',
  gt: '>',
  between: 'between',
  on: 'is',
  before: 'before',
  after: 'after',
}

/** How many values an operator needs: none, one, or a from/to pair. */
export function valuesNeeded(op: Operator): 0 | 1 | 2 {
  if (op === 'empty' || op === 'nempty') return 0
  return op === 'between' ? 2 : 1
}

export function isComplete(condition: Condition): boolean {
  const needed = valuesNeeded(condition.op)
  if (needed === 0) return true
  if (needed === 2) return Boolean(condition.values[0] && condition.values[1])
  return condition.values.some((v) => v !== '')
}

function kindOf(field: FieldSpec): FilterKind | null {
  switch (field.type) {
    case 'picklist':
    case 'multiselect':
    case 'lookup':
      return 'choice'
    case 'text':
    case 'longtext':
    case 'richtext':
    case 'email':
    case 'phone':
    case 'url':
      return 'text'
    case 'date':
    case 'datetime':
      // The same convention the importer reads: a *_month field holds the first of a month.
      return field.api_name.endsWith('_month') ? 'month' : 'date'
    case 'currency':
    case 'number':
    case 'percent':
      return 'number'
    case 'checkbox':
      return 'checkbox'
    default:
      return null // formulas, files, child lists, record ids
  }
}

/** "STAGE 3 — PRESCRIPTION" → "Stage 3 · Prescription". */
export function sectionLabel(section: string): string {
  if (section === '__header') return 'Record header'
  const words = section
    .replace(/\s*[—–-]\s*/g, ' · ')
    .toLowerCase()
    .replace(/\b([a-z])/g, (c) => c.toUpperCase())
  return words.replace(/\b(Poc|Rfp|Rfi|Si)\b/g, (w) => w.toUpperCase())
}

const SUFFIXES = ['_gte', '_lte', '_gt', '_lt', '_ne', '_is', '_isnt', '_contains', '_ncontains', '_starts', '_empty']

// ---- the URL form of one condition, and back

function lastDayOf(month: string): string {
  const [year, m] = month.split('-').map(Number)
  const day = new Date(Date.UTC(year, m, 0)).getUTCDate()
  return `${month}-${String(day).padStart(2, '0')}`
}

function encode(f: FilterField, { op, values }: Condition): Record<string, string[]> {
  const k = f.key
  const v = values[0] ?? ''
  if (op === 'empty') return { [`${k}_empty`]: ['1'] }
  if (op === 'nempty') return { [`${k}_empty`]: ['0'] }
  if (f.kind === 'checkbox') return v === 'false' ? { [`${k}_isnt`]: ['true'] } : { [`${k}_is`]: ['true'] }
  if (f.kind === 'choice') return op === 'isnt' ? { [`${k}_ne`]: values } : { [k]: values }
  if (f.kind === 'text') return { [`${k}_${op}`]: [v] }
  const month = f.kind === 'month'
  const start = (value: string) => (month ? `${value}-01` : value)
  // A day ends at 23:59:59, so "is 17 Sep" still holds a Created Time of 17 Sep 14:05.
  const end = (value: string) => (month ? lastDayOf(value) : f.kind === 'date' ? `${value}T23:59:59` : value)
  switch (op) {
    case 'eq':
    case 'on':
      return { [`${k}_gte`]: [start(v)], [`${k}_lte`]: [end(v)] }
    case 'lt':
    case 'before':
      return { [`${k}_lt`]: [start(v)] }
    case 'gt':
    case 'after':
      return { [`${k}_gt`]: [end(v)] }
    default:
      return { [`${k}_gte`]: [start(values[0] ?? '')], [`${k}_lte`]: [end(values[1] ?? '')] }
  }
}

function decode(f: FilterField, get: (key: string) => string[]): Condition | null {
  const k = f.key
  const one = (suffix: string) => get(`${k}${suffix}`).find((v) => v !== '')
  const empty = one('_empty')
  if (empty !== undefined) return { op: empty === '0' ? 'nempty' : 'empty', values: [] }
  if (f.kind === 'checkbox') {
    if (one('_is') === 'true') return { op: 'is', values: ['true'] }
    if (one('_isnt') === 'true') return { op: 'is', values: ['false'] }
    return null
  }
  if (f.kind === 'choice') {
    const is = get(k).filter(Boolean)
    if (is.length) return { op: 'is', values: is }
    const isnt = get(`${k}_ne`).filter(Boolean)
    return isnt.length ? { op: 'isnt', values: isnt } : null
  }
  if (f.kind === 'text') {
    for (const op of ['is', 'isnt', 'contains', 'ncontains', 'starts'] as const) {
      const v = one(`_${op}`)
      if (v !== undefined) return { op, values: [v] }
    }
    return null
  }
  const month = f.kind === 'month'
  const back = (value: string) => (month ? value.slice(0, 7) : f.kind === 'date' ? value.slice(0, 10) : value)
  const numberish = f.kind === 'number'
  const gte = one('_gte')
  const lte = one('_lte')
  if (gte !== undefined && lte !== undefined) {
    const same = month
      ? gte.slice(0, 7) === lte.slice(0, 7) && gte.endsWith('-01') && lte === lastDayOf(lte.slice(0, 7))
      : back(gte) === back(lte)
    if (same) return { op: numberish ? 'eq' : 'on', values: [back(gte)] }
    return { op: 'between', values: [back(gte), back(lte)] }
  }
  if (gte !== undefined) return { op: 'between', values: [back(gte), ''] }
  if (lte !== undefined) return { op: 'between', values: ['', back(lte)] }
  const lt = one('_lt')
  if (lt !== undefined) return { op: numberish ? 'lt' : 'before', values: [back(lt)] }
  const gt = one('_gt')
  if (gt !== undefined) return { op: numberish ? 'gt' : 'after', values: [back(gt)] }
  return null
}

// ---- the hook

export interface ListFilterOptions {
  /** The list_views key: its `filters` are the Common filters, its `search` the search box. */
  view: string
  /** The module whose fields are offered, when it differs from the view — Partners are accounts. */
  fieldModule?: string
  /** Only these register sections — a registration is the DEAL REGISTRATION section of partners. */
  sections?: string[]
  /** The stage field of a pipeline module — Kanban leaves it out, its columns ARE the stages. */
  stageField?: string
  /** Prefix for the URL keys, so two lists on one page keep separate filters. */
  prefix?: string
  /** Choices a field may offer on this screen — Partners offers partner account types only. */
  choiceLimits?: Record<string, string[]>
}

export interface ListFilters {
  module: string
  /** The list view's own filters — shown first in the panel. */
  common: FilterField[]
  /** Every other field of the module's own record, alphabetically. */
  others: FilterField[]
  /**
   * Which records this list shows by default — "Open leads" / "Converted leads"
   * / "All leads", as spec/extensions.json `list_scopes` declares them. Absent
   * on a module with no scope (Deals, Accounts, Contacts).
   */
  scope?: {
    options: ListScopeOption[]
    /** The option on now. Never empty when `scope` is present. */
    active: ListScopeOption
    set: (key: string) => void
    /**
     * True when someone has filtered the status field by hand, so the scope is
     * not being applied. The picker says so rather than silently lying.
     */
    overridden: boolean
  }
  stageField?: string
  choiceLimits?: Record<string, string[]>
  /** Free-text search, as typed. Outside the panel. */
  q: string
  setQ: (text: string) => void
  /** The conditions on now, by field key. */
  conditions: Record<string, Condition>
  /** Replace every condition at once — the panel's Apply. Incomplete ones are dropped. */
  apply: (next: Record<string, Condition>) => void
  remove: (key: string) => void
  clearAll: () => void
  /**
   * Parameters for the list endpoint. `withStage` false drops the stage
   * condition — on Kanban the columns are the stages.
   */
  params: (options?: { withStage?: boolean }) => Record<string, string | string[]>
}

export function useListFilters({ view: viewKey, fieldModule, sections, stageField, prefix = '', choiceLimits }: ListFilterOptions): ListFilters {
  const [searchParams, setSearchParams] = useSearchParams()
  const view = listViewFor(viewKey)
  const module = fieldModule ?? viewKey
  const scopeSpec = listScopeFor(viewKey)

  const sectionKey = sections?.join('|') ?? ''
  const { common, others, all } = useMemo(() => {
    const allowed = sectionKey ? new Set(sectionKey.split('|')) : null
    const toFilter = (field: FieldSpec): FilterField | null => {
      // A per-stage answer lives under <name>__s<stage>, never under the name itself.
      if (field.stage_scoped && field.stage_scoped !== 'none') return null
      const kind = kindOf(field)
      return kind ? { key: field.api_name, label: field.label, kind, field, section: sectionLabel(field.section) } : null
    }
    const pinned: FilterField[] = []
    for (const field of view?.filterFields ?? []) {
      const hit = toFilter(field)
      if (hit && !pinned.some((p) => p.key === hit.key)) pinned.push(hit)
    }
    const taken = new Set(pinned.map((f) => f.key))
    const rest: FilterField[] = []
    for (const field of fieldsOf(module)) {
      if (taken.has(field.api_name)) continue
      if (field.value_mode === 'read_through') continue // the parent's identity, not this record's
      if (allowed && !allowed.has(field.section)) continue
      const hit = toFilter(field)
      if (!hit) continue
      taken.add(hit.key)
      rest.push(hit)
    }
    rest.sort((a, b) => a.label.localeCompare(b.label))
    return { common: pinned, others: rest, all: [...pinned, ...rest] }
  }, [module, view, sectionKey])

  /** Every URL key the filters own, with the field it belongs to. Anything else on the URL is left alone. */
  const owned = useMemo(() => {
    const keys = new Map<string, string>()
    for (const f of all) {
      keys.set(f.key, f.key)
      for (const suffix of SUFFIXES) keys.set(`${f.key}${suffix}`, f.key)
    }
    return keys
  }, [all])

  const write = useCallback(
    (entries: Record<string, string[]>) =>
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current)
          for (const [key, values] of Object.entries(entries)) {
            next.delete(prefix + key)
            for (const value of values) if (value !== '') next.append(prefix + key, value)
          }
          return next
        },
        // A filter is a view setting, not a place: Back should leave the page,
        // not step through every checkbox.
        { replace: true }
      ),
    [setSearchParams, prefix]
  )

  const get = useCallback((key: string) => searchParams.getAll(prefix + key), [searchParams, prefix])

  const conditions = useMemo(() => {
    const out: Record<string, Condition> = {}
    for (const f of all) {
      const condition = decode(f, get)
      if (condition) out[f.key] = condition
    }
    return out
  }, [all, get])

  const cleared = useCallback(
    (keys: string[]) => {
      const out: Record<string, string[]> = {}
      for (const [key, fieldKey] of owned) if (keys.includes(fieldKey)) out[key] = []
      return out
    },
    [owned]
  )

  const apply = useCallback(
    (next: Record<string, Condition>) => {
      const entries = cleared(all.map((f) => f.key))
      for (const f of all) {
        const condition = next[f.key]
        if (condition && isComplete(condition)) Object.assign(entries, encode(f, condition))
      }
      write(entries)
    },
    [all, cleared, write]
  )

  const remove = useCallback((key: string) => write(cleared([key])), [cleared, write])
  const clearAll = useCallback(() => write(cleared(all.map((f) => f.key))), [all, cleared, write])
  const setQ = useCallback((text: string) => write({ q: text.trim() ? [text] : [] }), [write])
  const q = get('q')[0] ?? ''

  // The scope lives on the URL under `scope`, beside the field conditions, so a
  // "Converted leads" screen is a link like any other filtered one. Unprefixed
  // keys are per-list already; the prefix keeps two lists on one page apart.
  const scopeKey = `${prefix}scope`
  const activeScope = useMemo(() => {
    if (!scopeSpec) return undefined
    const wanted = searchParams.get(scopeKey) ?? scopeSpec.default
    const match = (key: string) => scopeSpec.options.find((option: ListScopeOption) => option.key === key)
    return match(wanted) ?? match(scopeSpec.default)
  }, [scopeSpec, searchParams, scopeKey])

  // An explicit condition on the status field wins. Two rules on one field
  // would intersect — "Open leads" plus "Status is Converted" is an empty list
  // that nothing on screen explains — so the hand-written one is the only one
  // sent, and the picker says it has stood down.
  const scopeOverridden = Boolean(scopeSpec && conditions[scopeSpec.field])

  const setScope = useCallback(
    (key: string) => {
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current)
          next.delete(scopeKey)
          if (scopeSpec && key !== scopeSpec.default) next.set(scopeKey, key)
          return next
        },
        { replace: true }
      )
    },
    [setSearchParams, scopeKey, scopeSpec]
  )

  const params = useCallback(
    ({ withStage = true }: { withStage?: boolean } = {}) => {
      const out: Record<string, string | string[]> = {}
      for (const [key, fieldKey] of owned) {
        if (!withStage && fieldKey === stageField) continue
        const values = get(key).filter((v) => v !== '')
        if (values.length) out[key] = values
      }
      applyScope(out, scopeSpec, activeScope, scopeOverridden)
      if (q.trim()) {
        out.q = q.trim()
        if (view?.search.length) out._search = view.search.join(',')
      }
      return out
    },
    [owned, get, stageField, q, view, scopeSpec, activeScope, scopeOverridden]
  )

  return {
    module,
    common,
    others,
    scope: scopeSpec && activeScope ? { options: scopeSpec.options, active: activeScope, set: setScope, overridden: scopeOverridden } : undefined,
    stageField,
    choiceLimits,
    q,
    setQ,
    conditions,
    apply,
    remove,
    clearAll,
    params,
  }
}

/**
 * Fold the chosen scope into the list parameters.
 *
 * `include` becomes repeated `<field>=KEY`, which the list contract reads as
 * OR; `exclude` becomes `<field>_ne=KEY`, which it reads as "isn't any of" —
 * see backend/app/list_query.py. An option with neither (All) adds nothing,
 * and so does a scope that a hand-written condition has overridden.
 *
 * The board asks for the same parameters as the list, so a converted pursuit
 * disappears from both together and the Converted column only ever holds what
 * the current scope admits.
 */
function applyScope(
  out: Record<string, string | string[]>,
  spec: ResolvedListScope | undefined,
  active: ListScopeOption | undefined,
  overridden: boolean
): void {
  if (!spec || !active || overridden) return
  if (active.include?.length) out[spec.field] = active.include
  else if (active.exclude?.length) out[`${spec.field}_ne`] = active.exclude
}
