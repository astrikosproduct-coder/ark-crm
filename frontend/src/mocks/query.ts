import {
  collectionFor,
  displayNameOf,
  fieldOf,
  fieldsOf,
  idOf,
  labelForValue,
  moduleForCollection,
} from '@/lib/spec'
import { withComputed } from '@/lib/spec/formula'
import { useDataStore } from '@/store/useDataStore'
import type { FieldSpec } from '@/types/field'

type Item = Record<string, unknown>

/**
 * List-endpoint semantics for the mock server.
 *
 * Paging, sorting and text search happen HERE rather than in the list
 * component, because that is where they will happen once a real backend
 * replaces MSW — CLAUDE.md rule 2. The component sends
 * `?_page=2&_limit=25&_sort=account_name&_order=desc&q=khazna` and reads the
 * total off the `X-Total-Count` header, exactly as it will in production.
 *
 * Any query parameter that is not one of the five reserved names is an equality
 * filter on that field, which is how an Account's related-contacts list asks for
 * `/api/contacts?account=ACC-001`.
 */

const RESERVED = new Set(['_page', '_limit', '_sort', '_order', '_search', 'q'])

/** Lookup targets served by the real backend rather than by the store. */
type Remote = Partial<Record<string, Item[]>>

export interface ListResult {
  rows: Item[]
  total: number
}

/**
 * id → display name for every lookup field of a module.
 *
 * Most targets resolve out of the store. `users` and `accounts` do not — they
 * are real database resources, and their rows are fetched by the handler and
 * passed in. See src/mocks/userDirectory.ts.
 */
function lookupLabels(
  module: string,
  remote: Remote
): Map<string, Map<string, string>> {
  const out = new Map<string, Map<string, string>>()

  for (const field of fieldsOf(module)) {
    if (field.type !== 'lookup') continue
    const target = collectionFor(field.lookup_target)
    if (!target) continue
    const rows = remote[target] ?? useDataStore.getState().list(target)
    if (!Array.isArray(rows)) continue

    const names = new Map<string, string>()
    for (const row of rows as Item[]) {
      const id = idOf(row)
      if (id) names.set(id, displayNameOf(row))
    }
    out.set(field.api_name, names)
  }

  return out
}

/** How a value reads when it is being searched or sorted as text. */
function textOf(field: FieldSpec, row: Item, labels: Map<string, Map<string, string>>): string {
  const value = row[field.api_name]
  if (value === null || value === undefined || value === '') return ''

  switch (field.type) {
    case 'lookup': {
      const id = String(value)
      return labels.get(field.api_name)?.get(id) ?? id
    }
    case 'picklist':
      return labelForValue(field.picklist, value)
    case 'multiselect':
      return Array.isArray(value)
        ? value.map((v) => labelForValue(field.picklist, v)).join(', ')
        : String(value)
    case 'checkbox':
      return value ? 'Yes' : 'No'
    default:
      return String(value)
  }
}

const NUMERIC = new Set(['number', 'currency', 'percent'])

function compareBy(field: FieldSpec, labels: Map<string, Map<string, string>>) {
  return (a: Item, b: Item): number => {
    const av = a[field.api_name]
    const bv = b[field.api_name]

    // Blanks sort last in either direction — an empty cell is not a low value.
    const aBlank = av === null || av === undefined || av === ''
    const bBlank = bv === null || bv === undefined || bv === ''
    if (aBlank && bBlank) return 0
    if (aBlank) return 1
    if (bBlank) return -1

    if (NUMERIC.has(field.type)) return Number(av) - Number(bv)

    return textOf(field, a, labels).localeCompare(textOf(field, b, labels), undefined, {
      sensitivity: 'base',
      numeric: true,
    })
  }
}

/**
 * A filter matches when the field equals one of the wanted values, or — for a
 * multiselect — when it contains one of them.
 *
 * Repeating a parameter ORs it rather than ANDing it, so the Partners screen can
 * ask for `?account_type=PARTNER_SI&account_type=OEM_TECHNOLOGY_PARTNER` and get
 * both. ANDing two values of the same field could never match anything, so no
 * caller loses a meaning it had before.
 */
function matchesFilter(value: unknown, wanted: string[]): boolean {
  if (Array.isArray(value)) return value.some((v) => wanted.includes(String(v)))
  return wanted.includes(String(value ?? ''))
}

export function runListQuery(
  collection: string,
  all: Item[],
  url: URL,
  /** Backend-served collections, already fetched by the handler. */
  remote: Remote = {}
): ListResult {
  const module = moduleForCollection(collection)
  const params = url.searchParams

  // Computed fields are never stored — see computeAll's own doc comment — so a
  // list row needs the same derivation a single-record view gets from
  // withComputed, or a column like leads.total_value_tcv would just read blank.
  let rows = module ? all.map((row) => withComputed(module, row)) : all

  // 1. equality filters on any field the caller names. Grouped first so that
  //    repeating a parameter is an OR over its values, not an impossible AND.
  const filters = new Map<string, string[]>()
  for (const [key, wanted] of params.entries()) {
    if (RESERVED.has(key)) continue
    filters.set(key, [...(filters.get(key) ?? []), wanted])
  }
  for (const [key, wanted] of filters) {
    rows = rows.filter((row) => matchesFilter(row[key], wanted))
  }

  const labels = module
    ? lookupLabels(module, remote)
    : new Map<string, Map<string, string>>()

  // 2. free-text search, over the fields the caller names or every field of the
  //    module when it names none
  const q = params.get('q')?.trim().toLowerCase()
  if (q && module) {
    const searchable = (params.get('_search')?.split(',') ?? [])
      .map((name) => fieldOf(module, name))
      .filter((f): f is FieldSpec => Boolean(f))
    const searchFields = searchable.length ? searchable : fieldsOf(module)
    rows = rows.filter((row) =>
      searchFields.some((f) => textOf(f, row, labels).toLowerCase().includes(q))
    )
  } else if (q) {
    rows = rows.filter((row) =>
      Object.values(row).some((v) => String(v ?? '').toLowerCase().includes(q))
    )
  }

  // 3. sort
  const sort = params.get('_sort')
  const field = module && sort ? fieldOf(module, sort) : undefined
  if (field) {
    const cmp = compareBy(field, labels)
    rows = [...rows].sort(cmp)
    if (params.get('_order') === 'desc') rows.reverse()
  }

  const total = rows.length

  // 4. page
  const page = Number(params.get('_page') ?? 0)
  const limit = Number(params.get('_limit') ?? 0)
  if (page > 0 && limit > 0) {
    rows = rows.slice((page - 1) * limit, page * limit)
  }

  // 5. join the lookup display names onto the page being returned, so the list
  //    never fires one request per row to resolve a name
  if (module && labels.size > 0) {
    rows = rows.map((row) => {
      const joined: Record<string, string> = {}
      for (const [apiName, names] of labels) {
        const id = row[apiName]
        if (typeof id === 'string' && id) joined[apiName] = names.get(id) ?? id
      }
      return Object.keys(joined).length ? { ...row, __labels: joined } : row
    })
  }

  return { rows, total }
}
